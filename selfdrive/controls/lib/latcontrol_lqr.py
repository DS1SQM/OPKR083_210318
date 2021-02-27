import numpy as np
from selfdrive.controls.lib.drive_helpers import get_steer_max
from common.numpy_fast import clip
from common.realtime import DT_CTRL
from cereal import log
from common.params import Params

class LatControlLQR():
  def __init__(self, CP):
    self.mpc_frame = 0
    self.params = Params()

    self.scale = CP.lateralTuning.lqr.scale
    self.ki = CP.lateralTuning.lqr.ki

    self.A = np.array(CP.lateralTuning.lqr.a).reshape((2, 2))
    self.B = np.array(CP.lateralTuning.lqr.b).reshape((2, 1))
    self.C = np.array(CP.lateralTuning.lqr.c).reshape((1, 2))
    self.K = np.array(CP.lateralTuning.lqr.k).reshape((1, 2))
    self.L = np.array(CP.lateralTuning.lqr.l).reshape((2, 1))
    self.dc_gain = CP.lateralTuning.lqr.dcGain

    self.x_hat = np.array([[0], [0]])
    self.i_unwind_rate = 0.3 * DT_CTRL
    self.i_rate = 1.0 * DT_CTRL

    self.sat_count_rate = 1.0 * DT_CTRL
    self.sat_limit = CP.steerLimitTimer

    self.reset()

  def reset(self):
    self.i_lqr = 0.0
    self.output_steer = 0.0
    self.sat_count = 0.0

  def live_tune(self, CP):
    self.mpc_frame += 1
    if self.mpc_frame % 300 == 0:
      self.scale_ = float(int(self.params.get('Scale')) * 1.0)
      self.ki_ = float(int(self.params.get('LqrKi')) * 0.001)
      self.dc_gain_ = float(int(self.params.get('DcGain')) * 0.0001)
      self.scale = self.scale_
      self.ki = self.ki_
      self.dc_gain = self.dc_gain_
        
      self.mpc_frame = 0

  def _check_saturation(self, control, check_saturation, limit):
    saturated = abs(control) == limit

    if saturated and check_saturation:
      self.sat_count += self.sat_count_rate
    else:
      self.sat_count -= self.sat_count_rate

    self.sat_count = clip(self.sat_count, 0.0, 1.0)

    return self.sat_count > self.sat_limit

  def update(self, active, CS, CP, lat_plan):
    if int(self.params.get("OpkrLiveTune", encoding='utf8')) == 1:
      self.live_tune(CP)

    lqr_log = log.ControlsState.LateralLQRState.new_message()

    steers_max = get_steer_max(CP, CS.vEgo)
    torque_scale = (0.45 + CS.vEgo / 60.0)**2  # Scale actuator model with speed

    steering_angle = CS.steeringAngleDeg

    # Subtract offset. Zero angle should correspond to zero torque
    self.angle_steers_des = lat_plan.steeringAngleDeg - lat_plan.angleOffsetDeg
    steering_angle -= lat_plan.angleOffsetDeg

    # Update Kalman filter
    angle_steers_k = float(self.C.dot(self.x_hat))
    e = steering_angle - angle_steers_k
    self.x_hat = self.A.dot(self.x_hat) + self.B.dot(CS.steeringTorqueEps / torque_scale) + self.L.dot(e)

    if CS.vEgo < 0.3 or not active:
      lqr_log.active = False
      lqr_output = 0.
      self.reset()
    else:
      lqr_log.active = True

      # LQR
      u_lqr = float(self.angle_steers_des / self.dc_gain - self.K.dot(self.x_hat))
      lqr_output = torque_scale * u_lqr / self.scale

      # Integrator
      if CS.steeringPressed:
        self.i_lqr -= self.i_unwind_rate * float(np.sign(self.i_lqr))
      else:
        error = self.angle_steers_des - angle_steers_k
        i = self.i_lqr + self.ki * self.i_rate * error
        control = lqr_output + i

        if (error >= 0 and (control <= steers_max or i < 0.0)) or \
           (error <= 0 and (control >= -steers_max or i > 0.0)):
          self.i_lqr = i

      self.output_steer = lqr_output + self.i_lqr
      self.output_steer = clip(self.output_steer, -steers_max, steers_max)

    check_saturation = (CS.vEgo > 10) and not CS.steeringRateLimited and not CS.steeringPressed
    saturated = self._check_saturation(self.output_steer, check_saturation, steers_max)

    lqr_log.steeringAngleDeg = angle_steers_k + lat_plan.angleOffsetDeg
    lqr_log.i = self.i_lqr
    lqr_log.output = self.output_steer
    lqr_log.lqrOutput = lqr_output
    lqr_log.saturated = saturated
    return self.output_steer, float(self.angle_steers_des), lqr_log
