#!/usr/bin/env python3
import datetime
import os
import signal
import subprocess
import sys
import traceback

import cereal.messaging as messaging
import selfdrive.crash as crash
from common.basedir import BASEDIR
from common.params import Params
from common.spinner import Spinner
from common.text_window import TextWindow
from selfdrive.hardware import EON, HARDWARE
from selfdrive.hardware.eon.apk import (pm_apply_packages, start_offroad,
                                        update_apks)
from selfdrive.manager.build import MAX_BUILD_PROGRESS, PREBUILT
from selfdrive.manager.helpers import unblock_stdout
from selfdrive.manager.process import ensure_running
from selfdrive.manager.process_config import managed_processes
from selfdrive.registration import register
from selfdrive.swaglog import add_logentries_handler, cloudlog
from selfdrive.version import dirty, version


def manager_init(spinner=None):
  params = Params()
  params.manager_start()

  default_params = [
    ("CommunityFeaturesToggle", "0"),
    ("CompletedTrainingVersion", "0"),
    ("IsRHD", "0"),
    ("IsMetric", "1"),
    ("RecordFront", "0"),
    ("HasAcceptedTerms", "0"),
    ("HasCompletedSetup", "0"),
    ("IsUploadRawEnabled", "0"),
    ("IsLdwEnabled", "1"),
    ("LastUpdateTime", datetime.datetime.utcnow().isoformat().encode('utf8')),
    ("OpenpilotEnabledToggle", "1"),
    ("VisionRadarToggle", "0"),
    ("LaneChangeEnabled", "1"),
    ("IsDriverViewEnabled", "0"),
    ("LimitSetSpeed", "0"),
    ("IsOpenpilotViewEnabled", "0"),
    ("OpkrAutoShutdown", "2"),
    ("OpkrAutoScreenOff", "0"),
    ("OpkrUIBrightness", "0"),
    ("OpkrEnableDriverMonitoring", "1"),
    ("OpkrEnableLogger", "0"),
    ("OpkrEnableGetoffAlert", "1"),
    ("OpkrAutoResume", "1"),
    ("OpkrVariableCruise", "1"),
    ("OpkrLaneChangeSpeed", "45"),
    ("OpkrAutoLaneChangeDelay", "0"),
    ("OpkrSteerAngleCorrection", "0"),
    ("PutPrebuiltOn", "0"),
    ("FingerprintIssuedFix", "0"),
    ("LdwsCarFix", "0"),
    ("LateralControlMethod", "0"),
    ("CruiseStatemodeSelInit", "1"),
    ("InnerLoopGain", "35"),
    ("OuterLoopGain", "20"),
    ("TimeConstant", "14"),
    ("ActuatorEffectiveness", "20"),
    ("Scale", "1750"),
    ("LqrKi", "10"),
    ("DcGain", "30"),
    ("IgnoreZone", "1"),
    ("PidKp", "30"),
    ("PidKi", "50"),
    ("PidKd", "150"),
    ("PidKf", "5"),
    ("CameraOffsetAdj", "60"),
    ("SteerRatioAdj", "150"),
    ("SteerRatioMaxAdj", "180"),
    ("SteerActuatorDelayAdj", "0"),
    ("SteerRateCostAdj", "45"),
    ("SteerLimitTimerAdj", "40"),
    ("TireStiffnessFactorAdj", "85"),
    ("SteerMaxAdj", "450"),
    ("SteerMaxBaseAdj", "280"),
    ("SteerDeltaUpAdj", "3"),
    ("SteerDeltaDownAdj", "7"),
    ("SteerMaxvAdj", "10"),
    ("OpkrBatteryChargingControl", "1"),
    ("OpkrBatteryChargingMin", "70"),
    ("OpkrBatteryChargingMax", "80"),
    ("OpkrUiOpen", "0"),
    ("OpkrDriveOpen", "0"),
    ("OpkrTuneOpen", "0"),
    ("OpkrControlOpen", "0"),
    ("LeftCurvOffsetAdj", "0"),
    ("RightCurvOffsetAdj", "0"),
    ("DebugUi1", "0"),
    ("DebugUi2", "0"),
    ("OpkrBlindSpotDetect", "1"),
    ("OpkrMaxAngleLimit", "90"),
    ("OpkrAutoResumeOption", "1"),
    ("OpkrSpeedLimitOffset", "0"),
    ("LimitSetSpeedCamera", "0"),
    ("LimitSetSpeedCameraDist", "0"),
    ("OpkrLiveSteerRatio", "1"),
    ("OpkrVariableSteerMax", "1"),
    ("OpkrVariableSteerDelta", "0"),
    ("FingerprintTwoSet", "1"),
    ("OpkrVariableCruiseProfile", "0"),
    ("OpkrLiveTune", "0"),
    ("OpkrDrivingRecord", "0"),
    ("OpkrTurnSteeringDisable", "0"),
    ("CarModel", ""),
    ("OpkrSafetyCamera", "0"),
    ("OpkrHotspotOnBoot", "0"),
    ("UserOption1", "0"),
    ("UserOption2", "0"),
    ("UserOption3", "0"),
    ("UserOption4", "0"),
    ("UserOption5", "0"),
    ("UserOption6", "0"),
    ("UserOption7", "0"),
    ("UserOption8", "0"),
    ("UserOption9", "0"),
    ("UserOption10", "0"),
    ("UserOptionName1", "설정속도를 현재속도에 동기화"),
    ("UserOptionName2", "Shane's FeedForward 활성화"),
    ("UserOptionName3", "저속 조향각 제한 활성화"),
    ("UserOptionName4", "가변크루즈 사용시 카메라감속만 사용"),
    ("UserOptionName5", ""),
    ("UserOptionName6", ""),
    ("UserOptionName7", ""),
    ("UserOptionName8", ""),
    ("UserOptionName9", ""),
    ("UserOptionName10", ""),
    ("UserOptionNameDescription1", "가변 크루즈 사용시 운전자 가속으로 인해 현재속도가 설정속도보다 높아질 경우 설정속도를 현재속도와 동기화 합니다."),
    ("UserOptionNameDescription2", "PID제어 사용시 Shane's FeedForward를 활성화 합니다. 직선구간에서는 토크를 낮추고 곡선구간에서는 토크를 높여 핸들 움직임을 능동적으로 합니다."),
    ("UserOptionNameDescription3", "저속 주행시 급격한 필요조향각 변화 시 현재조향각 변화를 제한하여 스티어링의 과도한 조향을 억제 합니다"),
    ("UserOptionNameDescription4", "가변크루즈 사용시 카메라감속기능만 사용합니다. 차간거리 및 커브구간 가속/감속 기능은 사용하지 않습니다. ※오파모드에서는 동작하지 않습니다."),
    ("UserOptionNameDescription5", ""),
    ("UserOptionNameDescription6", ""),
    ("UserOptionNameDescription7", ""),
    ("UserOptionNameDescription8", ""),
    ("UserOptionNameDescription9", ""),
    ("UserOptionNameDescription10", ""),
  ]

  # set unset params
  for k, v in default_params:
    if params.get(k) is None:
      params.put(k, v)

  # is this dashcam?
  if os.getenv("PASSIVE") is not None:
    params.put("Passive", str(int(os.getenv("PASSIVE"))))

  if params.get("Passive") is None:
    raise Exception("Passive must be set to continue")

  if EON:
    update_apks()

  os.umask(0)  # Make sure we can create files with 777 permissions

  # Create folders needed for msgq
  try:
    os.mkdir("/dev/shm")
  except FileExistsError:
    pass
  except PermissionError:
    print("WARNING: failed to make /dev/shm")

  # set dongle id
  reg_res = register(spinner)
  if reg_res:
    dongle_id = reg_res
  else:
    raise Exception("server registration failed")
  os.environ['DONGLE_ID'] = dongle_id  # Needed for swaglog and loggerd

  if not dirty:
    os.environ['CLEAN'] = '1'

  cloudlog.bind_global(dongle_id=dongle_id, version=version, dirty=dirty,
                       device=HARDWARE.get_device_type())
  crash.bind_user(id=dongle_id)
  crash.bind_extra(version=version, dirty=dirty, device=HARDWARE.get_device_type())

  # ensure shared libraries are readable by apks
  if EON:
    os.chmod(BASEDIR, 0o755)
    os.chmod("/dev/shm", 0o777)
    os.chmod(os.path.join(BASEDIR, "cereal"), 0o755)
    os.chmod(os.path.join(BASEDIR, "cereal", "libmessaging_shared.so"), 0o755)


def manager_prepare(spinner=None):
  # build all processes
  os.chdir(os.path.dirname(os.path.abspath(__file__)))

  total = 100.0 - (0 if PREBUILT else MAX_BUILD_PROGRESS)
  for i, p in enumerate(managed_processes.values()):
    p.prepare()
    if spinner:
      perc = (100.0 - total) + total * (i + 1) / len(managed_processes)
      spinner.update_progress(perc, 100.)


def manager_cleanup():
  if EON:
    pm_apply_packages('disable')

  for p in managed_processes.values():
    p.stop()

  cloudlog.info("everything is dead")


def manager_thread(spinner=None):
  cloudlog.info("manager start")
  cloudlog.info({"environ": os.environ})

  # save boot log
  subprocess.call("./bootlog", cwd=os.path.join(BASEDIR, "selfdrive/loggerd"))

  ignore = []
  if os.getenv("NOBOARD") is not None:
    ignore.append("pandad")
  if os.getenv("BLOCK") is not None:
    ignore += os.getenv("BLOCK").split(",")

  # start offroad
  if EON and "QT" not in os.environ:
    pm_apply_packages('enable')
    start_offroad()

  ensure_running(managed_processes.values(), started=False, not_run=ignore)
  if spinner:  # close spinner when ui has started
    spinner.close()

  started_prev = False
  params = Params()
  sm = messaging.SubMaster(['deviceState'])
  pm = messaging.PubMaster(['managerState'])

  while True:
    sm.update()
    not_run = ignore[:]

    if sm['deviceState'].freeSpacePercent < 5:
      not_run.append("loggerd")

    started = sm['deviceState'].started
    driverview = params.get("IsDriverViewEnabled") == b"1"
    ensure_running(managed_processes.values(), started, driverview, not_run)

    # trigger an update after going offroad
    #if started_prev and not started and 'updated' in managed_processes:
      #os.sync()
      #managed_processes['updated'].signal(signal.SIGHUP)

    started_prev = started

    running_list = ["%s%s\u001b[0m" % ("\u001b[32m" if p.proc.is_alive() else "\u001b[31m", p.name)
                    for p in managed_processes.values() if p.proc]
    cloudlog.debug(' '.join(running_list))

    # send managerState
    msg = messaging.new_message('managerState')
    msg.managerState.processes = [p.get_process_state_msg() for p in managed_processes.values()]
    pm.send('managerState', msg)

    # Exit main loop when uninstall is needed
    if params.get("DoUninstall", encoding='utf8') == "1":
      break


def main(spinner=None):
  manager_init(spinner)
  manager_prepare(spinner)

  if os.getenv("PREPAREONLY") is not None:
    return

  # SystemExit on sigterm
  signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(1))

  try:
    manager_thread(spinner)
  except Exception:
    traceback.print_exc()
    crash.capture_exception()
  finally:
    manager_cleanup()

  if Params().get("DoUninstall", encoding='utf8') == "1":
    cloudlog.warning("uninstalling")
    HARDWARE.uninstall()


if __name__ == "__main__":
  unblock_stdout()
  spinner = Spinner()
  spinner.update_progress(MAX_BUILD_PROGRESS, 100)

  try:
    main(spinner)
  except Exception:
    add_logentries_handler(cloudlog)
    cloudlog.exception("Manager failed to start")

    # Show last 3 lines of traceback
    error = traceback.format_exc(-3)
    error = "Manager failed to start\n\n" + error
    spinner.close()
    with TextWindow(error) as t:
      t.wait_for_exit()

    raise

  # manual exit because we are forked
  sys.exit(0)
