//! Display/performance settings from `assets/data/settings.ron`.

use bevy::prelude::*;
use serde::{Deserialize, Serialize};

use crate::asset_root;

#[derive(Resource, Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
pub struct Settings {
    pub width: u32,
    pub height: u32,
    pub fullscreen: bool,
    pub vsync: bool,
    pub msaa: u32,
    pub shadows: bool,
    pub shadow_cascades: usize,
    pub shadow_distance: f32,
    pub master_volume: f32,
    pub sound_enabled: bool,
    pub tick_hz: f32,
    /// Make every campaign level selectable regardless of progress (false = play them in order,
    /// as in the original).
    pub unlock_all_levels: bool,
    /// Folder of the player's own copy of the original Swarm Assault (the one holding
    /// `Game\Game.DDF`). Empty = look in the usual places (see original.rs).
    pub original_game_dir: String,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            width: 1280,
            height: 720,
            fullscreen: false,
            vsync: true,
            msaa: 4,
            shadows: true,
            shadow_cascades: 3,
            shadow_distance: 120.0,
            master_volume: 0.0,
            sound_enabled: true,
            tick_hz: 0.0,
            unlock_all_levels: false,
            original_game_dir: String::new(),
        }
    }
}

impl Settings {
    pub fn load() -> Self {
        let path = std::path::PathBuf::from(asset_root()).join("data/settings.ron");
        match std::fs::read_to_string(&path) {
            Ok(t) => match ron::from_str::<Settings>(sa_sim::data::strip_bom(&t)) {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("settings.ron invalid ({e}); using defaults");
                    Settings::default()
                }
            },
            Err(_) => Settings::default(),
        }
    }

    /// Writes the file back (keeping the comments of the shipped file).
    pub fn save(&self) {
        let path = std::path::PathBuf::from(asset_root()).join("data/settings.ron");
        let text = format!(
            "// Display / performance settings (read at start-up; the Settings dialog writes this file).\n(\n    width: {},\n    height: {},\n    fullscreen: {},\n    vsync: {},\n    msaa: {},            // 1, 2, 4 or 8 samples\n    shadows: {},\n    shadow_cascades: {},\n    shadow_distance: {:.1},\n    master_volume: {:.2},\n    sound_enabled: {},\n    // simulation ticks per second override (0 = use rules.ron)\n    tick_hz: {:.1},\n    // campaign levels unlock one after another (saves/progress.ron); true makes all selectable\n    unlock_all_levels: {},\n    // your copy of the original Swarm Assault (the folder holding Game\\Game.DDF): its ground,\n    // interface and sounds are used when found; empty = look next to / above the game folder\n    original_game_dir: {:?},\n)\n",
            self.width,
            self.height,
            self.fullscreen,
            self.vsync,
            self.msaa,
            self.shadows,
            self.shadow_cascades,
            self.shadow_distance,
            self.master_volume,
            self.sound_enabled,
            self.tick_hz,
            self.unlock_all_levels,
            self.original_game_dir
        );
        match std::fs::write(&path, text) {
            Ok(()) => info!("settings saved to {}", path.display()),
            Err(e) => error!("could not save {}: {e}", path.display()),
        }
    }

    pub fn msaa(&self) -> Msaa {
        match self.msaa {
            2 => Msaa::Sample2,
            4 => Msaa::Sample4,
            8 => Msaa::Sample8,
            _ => Msaa::Off,
        }
    }
}
