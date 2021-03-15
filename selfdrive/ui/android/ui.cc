#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <sys/resource.h>

#include <algorithm>

#include "common/framebuffer.h"
#include "common/util.h"
#include "common/params.h"
#include "common/swaglog.h"
#include "common/touch.h"
#include "common/watchdog.h"

#include "ui.hpp"
#include "paint.hpp"
#include "android/sl_sound.hpp"
#include "dashcam.h"
#include "latcontrol.h"

ExitHandler do_exit;
static void ui_set_brightness(UIState *s, int brightness) {
  static int last_brightness = -1;
  if (last_brightness != brightness && (s->awake || brightness == 0)) {
    if (set_brightness(brightness)) {
      last_brightness = brightness;
    }
  }
}

static void handle_display_state(UIState *s, FrameBuffer *fb, bool user_input) {
  if (user_input) {
    // 30 second timeout
    s->awake_timeout = (s->nOpkrAutoScreenOff && s->scene.started)? s->nOpkrAutoScreenOff*60*UI_FREQ : 30*UI_FREQ;
  }
  if (s->awake != user_input) {
    s->awake = user_input;
    // TODO: replace command_awake and command_sleep with direct calls to android
    if (user_input) {
      int display_mode = HWC_POWER_MODE_NORMAL;
      LOGW("setting display mode %d", display_mode);
      s->fb->set_power(display_mode);
      system("service call window 18 i32 1");
    } else {
      LOGW("awake off");
      ui_set_brightness(s, 0);
      system("service call window 18 i32 0");
    }
  }
}

static void handle_vision_touch(UIState *s, int touch_x, int touch_y) {
  if (s->scene.started && (touch_x >= s->viz_rect.x - bdr_s)
      && (s->active_app != cereal::UiLayoutState::App::SETTINGS)) {
    if (!s->scene.driver_view) {
      s->sidebar_collapsed = !s->sidebar_collapsed;
    } else {
      Params().write_db_value("IsDriverViewEnabled", "0", 1);
    }
  }
}

static void handle_sidebar_touch(UIState *s, int touch_x, int touch_y) {
  if (!s->sidebar_collapsed && touch_x <= sbr_w) {
    if (settings_btn.ptInRect(touch_x, touch_y)) {
      s->active_app = cereal::UiLayoutState::App::SETTINGS;
    } else if (home_btn.ptInRect(touch_x, touch_y)) {
      if (s->scene.started) {
        s->active_app = cereal::UiLayoutState::App::NONE;
        s->sidebar_collapsed = true;
      } else {
        s->active_app = cereal::UiLayoutState::App::HOME;
      }
    }
  }
}

static void update_offroad_layout_state(UIState *s, PubMaster *pm) {
  static int timeout = 0;
  static bool prev_collapsed = false;
  static cereal::UiLayoutState::App prev_app = cereal::UiLayoutState::App::NONE;
  if (timeout > 0) {
    timeout--;
  }
  if (prev_collapsed != s->sidebar_collapsed || prev_app != s->active_app || timeout == 0) {
    MessageBuilder msg;
    auto layout = msg.initEvent().initUiLayoutState();
    layout.setActiveApp(s->active_app);
    layout.setSidebarCollapsed(s->sidebar_collapsed);
    pm->send("offroadLayout", msg);
    LOGD("setting active app to %d with sidebar %d", (int)s->active_app, s->sidebar_collapsed);
    prev_collapsed = s->sidebar_collapsed;
    prev_app = s->active_app;
    timeout = 2 * UI_FREQ;
  }
}

int main(int argc, char* argv[]) {
  setpriority(PRIO_PROCESS, 0, -14);

  SLSound sound;
  UIState uistate = {};
  UIState *s = &uistate;
  FrameBuffer fb = FrameBuffer("ui", 0, true, &s->fb_w, &s->fb_h);

  ui_init(s);
  s->sound = &sound;

  TouchState touch = {0};
  touch_init(&touch);
  handle_display_state(s, &fb, true);

  PubMaster *pm = new PubMaster({"offroadLayout"});

  // light sensor scaling and volume params
  float brightness_b = 0, brightness_m = 0;
  int result = read_param(&brightness_b, "BRIGHTNESS_B", true);
  result += read_param(&brightness_m, "BRIGHTNESS_M", true);
  if (result != 0) {
    brightness_b = 10.0;
    brightness_m = 2.6;
    write_param_float(brightness_b, "BRIGHTNESS_B", true);
    write_param_float(brightness_m, "BRIGHTNESS_M", true);
  }
  float smooth_brightness = brightness_b;

  const int MIN_VOLUME = 12;
  const int MAX_VOLUME = 15;
  s->sound->setVolume(MIN_VOLUME);

  if (s->nOpkrAutoScreenOff && !s->awake) {
    handle_display_state(s, &fb, true);
  }

  while (!do_exit) {
    watchdog_kick();
    if (!s->scene.started) {
      util::sleep_for(50);
    }
    double u1 = millis_since_boot();

    ui_update(s);

    // manage wakefulness
    if (s->scene.started || s->scene.ignition) {
      if (s->nOpkrAutoScreenOff) {
        // turn on screen when alert is here.
        if (s->awake_timeout == 0 && (s->status == STATUS_DISENGAGED || s->status == STATUS_ALERT || s->status == STATUS_WARNING || (s->scene.alert_text1 != ""))) {
          handle_display_state(s, &fb, true);
        }
      } else {
        handle_display_state(s, &fb, true);
      }
    }

    if (s->awake_timeout > 0) {
      s->awake_timeout--;
    } else {
      handle_display_state(s, &fb, false);
    }

    // poll for touch events
    int touch_x = -1, touch_y = -1;
    int touched = touch_poll(&touch, &touch_x, &touch_y, 0);

    if ((s->awake) && (dashcam(s, touch_x, touch_y))) {
      touched = 0;
    }

    if ((s->awake) && (latcontrol(s, touch_x, touch_y))) {
      touched = 0;
    }

    if (touched == 1) {
      if (s->nOpkrAutoScreenOff && s->awake_timeout == 0) {
        handle_display_state(s, &fb, true);
      } else {
        handle_display_state(s, &fb, true);
        handle_sidebar_touch(s, touch_x, touch_y);
        handle_vision_touch(s, touch_x, touch_y);
      }
    }

    // Don't waste resources on drawing in case screen is off
    if (!s->awake) {
      continue;
    }

    // up one notch every 5 m/s
    float min = MIN_VOLUME + s->scene.car_state.getVEgo() / 5;
    if (s->nOpkrUIVolumeBoost > 0 || s->nOpkrUIVolumeBoost < 0) {
      min = min * (1 + s->nOpkrUIVolumeBoost * 0.01);
    }
    s->sound->setVolume(fmin(MAX_VOLUME, min)); // up one notch every 5 m/s

    // set brightness
    if (s->nOpkrUIBrightness == 0) {
    float clipped_brightness = (s->light_sensor*brightness_m) + brightness_b;
    if (clipped_brightness > 512) clipped_brightness = 512;
    smooth_brightness = clipped_brightness * 0.01 + smooth_brightness * 0.99;
    if (smooth_brightness > 255) smooth_brightness = 255;
    ui_set_brightness(s, (int)smooth_brightness);
    } else {
      ui_set_brightness(s, (int)(255*s->nOpkrUIBrightness*0.01));
    }

    update_offroad_layout_state(s, pm);

    ui_draw(s);
    double u2 = millis_since_boot();
    if (!s->scene.driver_view && (u2-u1 > 66)) {
      // warn on sub 15fps
      LOGW("slow frame(%llu) time: %.2f", (s->sm)->frame, u2-u1);
    }
    fb.swap();
  }

  handle_display_state(s, &fb, true);
  delete s->sm;
  delete pm;
  return 0;
}
