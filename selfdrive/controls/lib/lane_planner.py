from common.numpy_fast import interp
import numpy as np
from selfdrive.hardware import EON, TICI
from cereal import car, log
from common.params import Params

TRAJECTORY_SIZE = 33
# camera offset is meters from center car to camera
if EON:
  CAMERA_OFFSET = int(Params().get('CameraOffsetAdj')) * 0.001  # m from center car to camera
  CAMERA_OFFSET_A = (int(Params().get('CameraOffsetAdj')) * 0.001) - 0.1
elif TICI:
  CAMERA_OFFSET = -0.04
else:
  CAMERA_OFFSET = 0.0


class LanePlanner:
  def __init__(self):
    self.ll_t = np.zeros((TRAJECTORY_SIZE,))
    self.ll_x = np.zeros((TRAJECTORY_SIZE,))
    self.lll_y = np.zeros((TRAJECTORY_SIZE,))
    self.rll_y = np.zeros((TRAJECTORY_SIZE,))
    self.lane_width_estimate = 3.7
    self.lane_width_certainty = 1.0
    self.lane_width = 3.7

    self.lll_prob = 0.
    self.rll_prob = 0.
    self.d_prob = 0.

    self.lll_std = 0.
    self.rll_std = 0.

    self.l_lane_change_prob = 0.
    self.r_lane_change_prob = 0.


  def parse_model(self, md, sm, v_ego):
    curvature = sm['controlsState'].curvature
    mode_select = sm['carState'].cruiseState.modeSel
    Curv = round(curvature, 4)
    # right lane is minus
    lane_differ = round(abs(self.lll_y[0] + self.rll_y[0]), 2)
    lean_offset = 0

    if mode_select == 3:
      lean_offset = -0.1
    else:
      lean_offset = 0

    if (int(Params().get("LeftCurvOffsetAdj", encoding='utf8')) != 0 or int(Params().get("RightCurvOffsetAdj", encoding='utf8')) != 0) and v_ego > 8:
      leftCurvOffsetAdj = int(Params().get("LeftCurvOffsetAdj", encoding='utf8'))
      rightCurvOffsetAdj = int(Params().get("RightCurvOffsetAdj", encoding='utf8'))
      if curvature > 0.0008 and leftCurvOffsetAdj < 0 and lane_differ >= 0: # left curve
        if lane_differ > 0.6:
          lane_differ = 0.6          
        lean_offset = +(abs(leftCurvOffsetAdj) * lane_differ * 0.05) # move to left
      elif curvature > 0.0008 and leftCurvOffsetAdj > 0 and lane_differ <= 0:
        if lane_differ > 0.6:
          lane_differ = 0.6
        lean_offset = -(abs(leftCurvOffsetAdj) * lane_differ * 0.05) # move to right
      elif curvature < -0.0008 and rightCurvOffsetAdj < 0 and lane_differ >= 0: # right curve
        if lane_differ > 0.6:
          lane_differ = 0.6    
        lean_offset = +(abs(rightCurvOffsetAdj) * lane_differ * 0.05) # move to left
      elif curvature < -0.0008 and rightCurvOffsetAdj > 0 and lane_differ <= 0:
        if lane_differ > 0.6:
          lane_differ = 0.6    
        lean_offset = -(abs(rightCurvOffsetAdj) * lane_differ * 0.05) # move to right
      else:
        lean_offset = 0

    if len(md.laneLines) == 4 and len(md.laneLines[0].t) == TRAJECTORY_SIZE:
      self.ll_t = (np.array(md.laneLines[1].t) + np.array(md.laneLines[2].t))/2
      # left and right ll x is the same
      self.ll_x = md.laneLines[1].x
      # only offset left and right lane lines; offsetting path does not make sense
      self.lll_y = np.array(md.laneLines[1].y) - CAMERA_OFFSET + lean_offset
      self.rll_y = np.array(md.laneLines[2].y) - CAMERA_OFFSET + lean_offset
      self.lll_prob = md.laneLineProbs[1]
      self.rll_prob = md.laneLineProbs[2]
      self.lll_std = md.laneLineStds[1]
      self.rll_std = md.laneLineStds[2]

    if len(md.meta.desireState):
      self.l_lane_change_prob = md.meta.desireState[log.LateralPlan.Desire.laneChangeLeft]
      self.r_lane_change_prob = md.meta.desireState[log.LateralPlan.Desire.laneChangeRight]

  def get_d_path(self, v_ego, path_t, path_xyz):
    # Reduce reliance on lanelines that are too far apart or
    # will be in a few seconds
    l_prob, r_prob = self.lll_prob, self.rll_prob
    width_pts = self.rll_y - self.lll_y
    prob_mods = []
    for t_check in [0.0, 1.5, 3.0]:
      width_at_t = interp(t_check * (v_ego + 7), self.ll_x, width_pts)
      prob_mods.append(interp(width_at_t, [4.0, 5.0], [1.0, 0.0]))
    mod = min(prob_mods)
    l_prob *= mod
    r_prob *= mod

    # Reduce reliance on uncertain lanelines
    l_std_mod = interp(self.lll_std, [.15, .3], [1.0, 0.0])
    r_std_mod = interp(self.rll_std, [.15, .3], [1.0, 0.0])
    l_prob *= l_std_mod
    r_prob *= r_std_mod

    # Find current lanewidth
    self.lane_width_certainty += 0.05 * (l_prob * r_prob - self.lane_width_certainty)
    current_lane_width = abs(self.rll_y[0] - self.lll_y[0])
    self.lane_width_estimate += 0.005 * (current_lane_width - self.lane_width_estimate)
    speed_lane_width = interp(v_ego, [0., 31.], [2.8, 3.5])
    self.lane_width = self.lane_width_certainty * self.lane_width_estimate + \
                      (1 - self.lane_width_certainty) * speed_lane_width

    clipped_lane_width = min(4.0, self.lane_width)
    path_from_left_lane = self.lll_y + clipped_lane_width / 2.0
    path_from_right_lane = self.rll_y - clipped_lane_width / 2.0

    self.d_prob = l_prob + r_prob - l_prob * r_prob
    lane_path_y = (l_prob * path_from_left_lane + r_prob * path_from_right_lane) / (l_prob + r_prob + 0.0001)
    lane_path_y_interp = np.interp(path_t, self.ll_t, lane_path_y)
    path_xyz[:,1] = self.d_prob * lane_path_y_interp + (1.0 - self.d_prob) * path_xyz[:,1]
    return path_xyz
