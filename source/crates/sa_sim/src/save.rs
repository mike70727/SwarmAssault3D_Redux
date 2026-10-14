//! Save/load: the whole [`World`] is serialised with RON (human-readable, editable).

use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::world::World;

#[derive(Serialize, Deserialize)]
pub struct SaveFile {
    pub version: String,
    pub world: World,
}

#[derive(Debug)]
pub enum SaveError {
    Io(std::io::Error),
    Format(String),
    Version { file: String, expected: String },
}

impl std::fmt::Display for SaveError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SaveError::Io(e) => write!(f, "io: {e}"),
            SaveError::Format(e) => write!(f, "format: {e}"),
            SaveError::Version { file, expected } => write!(f, "save version {file} does not match {expected}"),
        }
    }
}

impl std::error::Error for SaveError {}

impl From<std::io::Error> for SaveError {
    fn from(e: std::io::Error) -> Self {
        SaveError::Io(e)
    }
}

pub fn to_string(world: &World) -> Result<String, SaveError> {
    let s = SaveFile { version: crate::version().to_string(), world: world.clone() };
    ron::ser::to_string_pretty(&s, ron::ser::PrettyConfig::new().depth_limit(6)).map_err(|e| SaveError::Format(e.to_string()))
}

pub fn from_str(text: &str) -> Result<World, SaveError> {
    let s: SaveFile = ron::from_str(text).map_err(|e| SaveError::Format(e.to_string()))?;
    if s.version != crate::version() {
        return Err(SaveError::Version { file: s.version, expected: crate::version().to_string() });
    }
    Ok(s.world)
}

pub fn save(world: &World, path: &Path) -> Result<(), SaveError> {
    let text = to_string(world)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(path, text)?;
    Ok(())
}

pub fn load(path: &Path) -> Result<World, SaveError> {
    let text = std::fs::read_to_string(path)?;
    from_str(&text)
}
