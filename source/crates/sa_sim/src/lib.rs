//! `sa_sim` – deterministic, render-free gameplay simulation for the Swarm Assault 3D recreation.
//!
//! The crate knows nothing about Bevy. It owns the map/navigation grid, units, weapons,
//! projectiles, colonies (including the colony-bit capture flow), bots, orders, victory rules and
//! save/load. The game crate advances it with [`World::step`] at a fixed rate and mirrors its state.
//!
//! Coordinate system: 2-D ground plane, `x` = east, `y` = south (so that the Bevy mapping is
//! `(x, 0, y)`), 1.0 = one map cell (one OpenSA/OpenRA cell). Headings are radians measured from
//! `+y` towards `+x` (`heading_to_dir`).

pub mod ai;
pub mod data;
pub mod events;
pub mod grid;
pub mod save;
pub mod spatial;
pub mod world;

pub use data::*;
pub use events::SimEvent;
pub use glam::{IVec2, Vec2};
pub use grid::NavGrid;
pub use world::*;

/// Crate version (useful for save-file compatibility checks).
pub fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Unit direction for a heading (radians, 0 = +y, grows towards +x).
pub fn heading_to_dir(h: f32) -> Vec2 {
    Vec2::new(h.sin(), h.cos())
}

/// Heading (radians) of a direction vector; zero vectors give 0.
pub fn dir_to_heading(d: Vec2) -> f32 {
    if d.length_squared() < 1e-8 { 0.0 } else { d.x.atan2(d.y) }
}

/// Shortest signed angular difference `b - a` in `[-pi, pi]`.
pub fn angle_diff(a: f32, b: f32) -> f32 {
    let mut d = (b - a) % std::f32::consts::TAU;
    if d > std::f32::consts::PI {
        d -= std::f32::consts::TAU;
    } else if d < -std::f32::consts::PI {
        d += std::f32::consts::TAU;
    }
    d
}

/// Move angle `a` towards `b` by at most `max_step` radians.
pub fn turn_towards(a: f32, b: f32, max_step: f32) -> f32 {
    let d = angle_diff(a, b);
    if d.abs() <= max_step { b } else { a + d.signum() * max_step }
}
