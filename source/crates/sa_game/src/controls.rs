//! Configurable key bindings loaded from `assets/data/controls.ron`.

use std::collections::HashMap;

use bevy::prelude::*;
use serde::{Deserialize, Serialize};

use crate::asset_root;

#[derive(Resource, Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct Controls {
    /// action name -> list of key names (any of them triggers the action)
    pub keys: HashMap<String, Vec<String>>,
    pub edge_pan: bool,
    pub edge_pan_margin: f32,
    pub pan_speed: f32,
    pub zoom_speed: f32,
    pub rotate_speed: f32,
    pub invert_zoom: bool,
    pub drag_threshold: f32,
}

impl Default for Controls {
    fn default() -> Self {
        let mut keys = HashMap::new();
        let mut bind = |a: &str, k: &[&str]| {
            keys.insert(a.to_string(), k.iter().map(|s| s.to_string()).collect::<Vec<_>>());
        };
        bind("pan_up", &["KeyW", "ArrowUp"]);
        bind("pan_down", &["KeyS", "ArrowDown"]);
        bind("pan_left", &["KeyA", "ArrowLeft"]);
        bind("pan_right", &["KeyD", "ArrowRight"]);
        bind("rotate_left", &["KeyQ"]);
        bind("rotate_right", &["KeyE"]);
        bind("zoom_in", &["Equal", "NumpadAdd"]);
        bind("zoom_out", &["Minus", "NumpadSubtract"]);
        bind("select_all", &["KeyC"]);
        bind("add_to_selection", &["ShiftLeft", "ShiftRight"]);
        bind("attack_move", &["KeyT"]);
        bind("stop", &["KeyX"]);
        bind("pause", &["Space"]);
        bind("speed_up", &["BracketRight"]);
        bind("speed_down", &["BracketLeft"]);
        bind("breed_1", &["Digit1"]);
        bind("breed_2", &["Digit2"]);
        bind("breed_3", &["Digit3"]);
        bind("breed_stop", &["Digit0"]);
        bind("set_rally", &["KeyR"]);
        bind("screenshot", &["F12"]);
        bind("debug_nav", &["F3"]);
        bind("quick_save", &["F5"]);
        bind("quick_load", &["F9"]);
        bind("menu", &["Escape"]);
        bind("center_camera", &["Home"]);
        bind("help", &["F1"]);
        bind("console", &["Enter", "NumpadEnter"]);
        Self { keys, edge_pan: true, edge_pan_margin: 12.0, pan_speed: 28.0, zoom_speed: 1.0, rotate_speed: 1.6, invert_zoom: false, drag_threshold: 6.0 }
    }
}

impl Controls {
    fn key_codes(&self, action: &str) -> impl Iterator<Item = KeyCode> + '_ {
        self.keys.get(action).into_iter().flatten().filter_map(|k| parse_key(k))
    }

    pub fn pressed(&self, input: &ButtonInput<KeyCode>, action: &str) -> bool {
        self.key_codes(action).any(|k| input.pressed(k))
    }

    pub fn just_pressed(&self, input: &ButtonInput<KeyCode>, action: &str) -> bool {
        self.key_codes(action).any(|k| input.just_pressed(k))
    }

    pub fn load() -> Self {
        let path = std::path::PathBuf::from(asset_root()).join("data/controls.ron");
        match std::fs::read_to_string(&path) {
            Ok(text) => match ron::from_str::<Controls>(sa_sim::data::strip_bom(&text)) {
                Ok(c) => c,
                Err(e) => {
                    warn!("controls.ron is invalid ({e}); using defaults");
                    Controls::default()
                }
            },
            Err(_) => {
                info!("no controls.ron found at {}; using defaults", path.display());
                Controls::default()
            }
        }
    }
}

/// Parse a key name as written in controls.ron (the `KeyCode` variant names).
pub fn parse_key(name: &str) -> Option<KeyCode> {
    use KeyCode::*;
    Some(match name {
        "KeyA" => KeyA, "KeyB" => KeyB, "KeyC" => KeyC, "KeyD" => KeyD, "KeyE" => KeyE, "KeyF" => KeyF,
        "KeyG" => KeyG, "KeyH" => KeyH, "KeyI" => KeyI, "KeyJ" => KeyJ, "KeyK" => KeyK, "KeyL" => KeyL,
        "KeyM" => KeyM, "KeyN" => KeyN, "KeyO" => KeyO, "KeyP" => KeyP, "KeyQ" => KeyQ, "KeyR" => KeyR,
        "KeyS" => KeyS, "KeyT" => KeyT, "KeyU" => KeyU, "KeyV" => KeyV, "KeyW" => KeyW, "KeyX" => KeyX,
        "KeyY" => KeyY, "KeyZ" => KeyZ,
        "Digit0" => Digit0, "Digit1" => Digit1, "Digit2" => Digit2, "Digit3" => Digit3, "Digit4" => Digit4,
        "Digit5" => Digit5, "Digit6" => Digit6, "Digit7" => Digit7, "Digit8" => Digit8, "Digit9" => Digit9,
        "ArrowUp" => ArrowUp, "ArrowDown" => ArrowDown, "ArrowLeft" => ArrowLeft, "ArrowRight" => ArrowRight,
        "Space" => Space, "Escape" => Escape, "Enter" => Enter, "NumpadEnter" => NumpadEnter, "Tab" => Tab, "Backspace" => Backspace,
        "ShiftLeft" => ShiftLeft, "ShiftRight" => ShiftRight, "ControlLeft" => ControlLeft, "ControlRight" => ControlRight,
        "AltLeft" => AltLeft, "AltRight" => AltRight, "Home" => Home, "End" => End, "PageUp" => PageUp, "PageDown" => PageDown,
        "Equal" => Equal, "Minus" => Minus, "BracketLeft" => BracketLeft, "BracketRight" => BracketRight,
        "NumpadAdd" => NumpadAdd, "NumpadSubtract" => NumpadSubtract, "Comma" => Comma, "Period" => Period,
        "F1" => F1, "F2" => F2, "F3" => F3, "F4" => F4, "F5" => F5, "F6" => F6, "F7" => F7, "F8" => F8,
        "F9" => F9, "F10" => F10, "F11" => F11, "F12" => F12,
        _ => return None,
    })
}

pub struct ControlsPlugin;

impl Plugin for ControlsPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(Controls::load());
    }
}
