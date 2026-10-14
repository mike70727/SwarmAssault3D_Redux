//! One-shot notifications the simulation emits each tick for the render/audio layers.

use glam::Vec2;
use serde::{Deserialize, Serialize};

use crate::world::{Target, UnitId};

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub enum SimEvent {
    UnitSpawned(UnitId),
    /// The unit started its death animation (still exists as a corpse).
    UnitDied(UnitId),
    /// The unit entity is gone for good.
    UnitRemoved(UnitId),
    /// A unit started an attack animation (`seq` increments per attack so repeats are visible).
    AttackStarted { unit: UnitId, target: Target, seq: u32 },
    ProjectileSpawned(u32),
    ProjectileRemoved(u32),
    /// Weapon impact at a ground position (effect id is from the weapon definition).
    Impact { pos: Vec2, effect: String, sound: String },
    ColonyDefeated(u32),
    /// A defeated colony scattered its bits.
    ColonyScattered(u32),
    ColonyCaptured { colony: u32, team: u8 },
    BitSpawned(u32),
    BitPicked { bit: u32, unit: UnitId, team: u8 },
    BitExpired(u32),
    /// Turret `turret` on colony `colony` fired (render hook: barrel recoil / muzzle flash).
    TurretFired { colony: u32, turret: usize },
    UnitParalyzed(UnitId),
    /// Generic positional audio hook.
    Sound { id: String, pos: Vec2 },
    TeamDefeated(u8),
    Victory(u8),
    /// Pirate ants emerged from an ant hole at `pos` (render hook: place an ant-hole prop).
    PirateSpawn { pos: Vec2, count: u32 },
    /// A neutral flyer entered the map.
    FlyerSpawn(UnitId),
}
