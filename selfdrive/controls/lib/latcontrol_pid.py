from selfdrive.controls.lib.pid import LatPIDController
from selfdrive.controls.lib.drive_helpers import get_steer_max
from cereal import car
from cereal import log
from common.params import Params


class LatControlPID():
  def __init__(self, CP):
    self.pid = LatPIDController((CP.lateralTuning.pid.kpBP, CP.lateralTuning.pid.kpV),
                                (CP.lateralTuning.pid.kiBP, CP.lateralTuning.pid.kiV),
                                (CP.lateralTuning.pid.kdBP, CP.lateralTuning.pid.kdV),
                                k_f=CP.lateralTuning.pid.kf, pos_limit=1.0, sat_limit=CP.steerLimitTimer)
    self.new_kf_tuned = CP.lateralTuning.pid.newKfTuned
    self.angle_steers_des = 0.
    self.mpc_frame = 0
    self.params = Params()

  def reset(self):
    self.pid.reset()

  # live tune referred to kegman's 
  def live_tune(self, CP):
    self.mpc_frame += 1
    if self.mpc_frame % 300 == 0:
      self.steerKpV = float(int(self.params.get('PidKp')) * 0.01)
      self.steerKiV = float(int(self.params.get('PidKi')) * 0.001)
      self.steerKdV = float(int(self.params.get('PidKd')) * 0.01)
      self.steerKf = float(int(self.params.get('PidKf')) * 0.00001)
      self.pid = LatPIDController((CP.lateralTuning.pid.kpBP, [0.1, self.steerKpV]),
                          (CP.lateralTuning.pid.kiBP, [0.01, self.steerKiV]),
                          (CP.lateralTuning.pid.kdBP, [self.steerKdV]),
                          k_f=self.steerKf, pos_limit=1.0)
      self.mpc_frame = 0

  def update(self, active, CS, CP, lat_plan):
    if self.params.get("OpkrLiveTune", encoding='utf8') is not None:
      if int(self.params.get("OpkrLiveTune", encoding='utf8')) == 1:
        self.live_tune(CP)

    pid_log = log.ControlsState.LateralPIDState.new_message()
    pid_log.steeringAngleDeg = float(CS.steeringAngleDeg)
    pid_log.steeringRateDeg = float(CS.steeringRateDeg)

    if CS.vEgo < 0.3 or not active:
      output_steer = 0.0
      pid_log.active = False
      self.pid.reset()
    else:
      self.angle_steers_des = lat_plan.steeringAngleDeg # get from MPC/LateralPlanner

      steers_max = get_steer_max(CP, CS.vEgo)
      self.pid.pos_limit = steers_max
      self.pid.neg_limit = -steers_max
      steer_feedforward = self.angle_steers_des   # feedforward desired angle
      if CP.steerControlType == car.CarParams.SteerControlType.torque:
        # TODO: feedforward something based on lat_plan.rateSteers
        steer_feedforward -= lat_plan.angleOffsetDeg # subtract the offset, since it does not contribute to resistive torque
        if self.new_kf_tuned:
          _c1, _c2, _c3 = 0.35189607550172824, 7.506201251644202, 69.226826411091
          steer_feedforward *= _c1 * CS.vEgo ** 2 + _c2 * CS.vEgo + _c3
        else:
          steer_feedforward *= CS.vEgo**2  # proportional to realigning tire momentum (~ lateral accel)
      deadzone = float(int(self.params.get('IgnoreZone')) * 0.1)

      check_saturation = (CS.vEgo > 10) and not CS.steeringRateLimited and not CS.steeringPressed
      output_steer = self.pid.update(self.angle_steers_des, CS.steeringAngleDeg, check_saturation=check_saturation, override=CS.steeringPressed,
                                     feedforward=steer_feedforward, speed=CS.vEgo, deadzone=deadzone)
      pid_log.active = True
      pid_log.p = self.pid.p
      pid_log.i = self.pid.i
      pid_log.f = self.pid.f
      pid_log.output = output_steer
      pid_log.saturated = bool(self.pid.saturated)

    return output_steer, float(self.angle_steers_des), pid_log
