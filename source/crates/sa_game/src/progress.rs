//! Campaign progress: the highest completed level number (levels unlock in order, as in the
//! original) and the "unlock everything" cheat. Stored in saves/progress.ron.

use bevy::prelude::*;
use serde::{Deserialize, Serialize};

const PATH: &str = "saves/progress.ron";

#[derive(Resource, Serialize, Deserialize, Clone, Debug, Default)]
#[serde(default)]
pub struct Progress {
    /// Highest campaign level number completed.
    pub completed: u32,
    /// Set by the console cheat: every level is selectable.
    pub unlocked_all: bool,
    /// File name of the last level played.
    pub last_level: Option<String>,
}

impl Progress {
    pub fn load() -> Self {
        match std::fs::read_to_string(PATH) {
            Ok(text) => ron::from_str(&text).unwrap_or_else(|e| {
                warn!("{PATH}: {e}; starting a fresh progress file");
                Self::default()
            }),
            Err(_) => Self::default(),
        }
    }

    pub fn save(&self) {
        std::fs::create_dir_all("saves").ok();
        match ron::ser::to_string_pretty(self, ron::ser::PrettyConfig::new()) {
            Ok(text) => {
                if let Err(e) = std::fs::write(PATH, text) {
                    error!("could not write {PATH}: {e}");
                }
            }
            Err(e) => error!("progress: {e}"),
        }
    }

    /// Whether a campaign level may be played. Custom and skirmish maps (no number) always may.
    pub fn is_unlocked(&self, number: Option<u32>, settings_unlock_all: bool) -> bool {
        match number {
            Some(n) => settings_unlock_all || self.unlocked_all || n <= self.completed + 1,
            None => true,
        }
    }

    /// Record a won campaign level; returns true when this is a new record.
    pub fn complete(&mut self, number: u32) -> bool {
        if number > self.completed {
            self.completed = number;
            self.save();
            true
        } else {
            false
        }
    }
}
