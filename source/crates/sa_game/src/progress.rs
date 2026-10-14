//! Campaign progress: the highest completed level number (levels unlock in order, as in the
//! original) and the "unlock everything" cheat. Stored in saves/progress.ron.

use bevy::prelude::*;
use serde::{Deserialize, Serialize};

fn path() -> std::path::PathBuf {
    crate::user_path("saves/progress.ron")
}

#[derive(Resource, Serialize, Deserialize, Clone, Debug, Default)]
#[serde(default)]
pub struct Progress {
    /// Highest campaign level number completed.
    pub completed: u32,
    /// Set by the console cheat: every level is selectable.
    pub unlocked_all: bool,
    /// File name of the last level played.
    pub last_level: Option<String>,
    /// Procedural mode (unlocked by finishing the campaign): the seed of the current run (0 = none
    /// started), the level to play next and the best level won.
    pub procedural_seed: u64,
    pub procedural_level: u32,
    pub procedural_best: u32,
}

/// Map name of a procedural level: "procedural:<level>:<run seed>" (sim_plugin.rs generates it).
pub fn procedural_map_name(level: u32, seed: u64) -> String {
    format!("procedural:{level}:{seed}")
}

/// Level and run seed of a procedural map name.
pub fn parse_procedural(name: &str) -> Option<(u32, u64)> {
    let mut parts = name.strip_prefix("procedural:")?.split(':');
    let level = parts.next()?.parse().ok()?;
    let seed = parts.next()?.parse().ok()?;
    Some((level, seed))
}

impl Progress {
    pub fn load() -> Self {
        let p = path();
        match std::fs::read_to_string(&p) {
            Ok(text) => ron::from_str(sa_sim::data::strip_bom(&text)).unwrap_or_else(|e| {
                warn!("{}: {e}; starting a fresh progress file", p.display());
                Self::default()
            }),
            Err(_) => Self::default(),
        }
    }

    pub fn save(&self) {
        let p = path();
        if let Some(dir) = p.parent() {
            std::fs::create_dir_all(dir).ok();
        }
        match ron::ser::to_string_pretty(self, ron::ser::PrettyConfig::new()) {
            Ok(text) => {
                if let Err(e) = std::fs::write(&p, text) {
                    error!("could not write {}: {e}", p.display());
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

    /// Procedural mode opens once the whole campaign is won (or with "unlock everything").
    pub fn procedural_unlocked(&self, settings_unlock_all: bool) -> bool {
        settings_unlock_all || self.unlocked_all || self.completed >= 100
    }

    /// The procedural level to play now; the first visit starts a run with a new seed.
    pub fn procedural_map(&mut self) -> String {
        if self.procedural_seed == 0 {
            let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos() as u64).unwrap_or(1);
            self.procedural_seed = now | 1;
            self.procedural_level = 1;
            self.save();
        }
        procedural_map_name(self.procedural_level.max(1), self.procedural_seed)
    }

    /// Record a won procedural level of the run `seed`: the next one is up.
    pub fn procedural_won(&mut self, level: u32, seed: u64) {
        if self.procedural_seed == 0 {
            self.procedural_seed = seed;
        }
        if seed == self.procedural_seed {
            self.procedural_level = self.procedural_level.max(level + 1);
            self.procedural_best = self.procedural_best.max(level);
            self.save();
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
