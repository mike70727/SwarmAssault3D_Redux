//! The neutral creep plants in 3-D: Popcorn Plant, Thorn Bush, Seed Ball and its seeds, Choc Freckle
//! and the four Death Lollies, modelled on the original sprites (OBWHIPPL, OBTHORNB, OBPUFFBL,
//! FRECKLE, OBLOLLYB/O/P/S). They are built in code from vertex-coloured meshes so that every part
//! can move: a plant grows in from a sprout, the Popcorn Plant's bud pops when it fires, the Seed
//! Ball's four husks split open whenever it throws, the Choc Freckle turns while it sprays, a badly
//! hurt plant droops, and a dead lolly leaves its broken shell.

use std::collections::HashMap;
use std::f32::consts::{PI, TAU};

use bevy::asset::RenderAssetUsages;
use bevy::mesh::{Indices, PrimitiveTopology, VertexAttributeValues};
use bevy::prelude::*;
use sa_sim::{UnitId, UnitState};

use crate::AppState;
use crate::sim_plugin::GameSim;

pub struct PlantsPlugin;

impl Plugin for PlantsPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, build_plant_assets).add_systems(Update, animate_plants.run_if(in_state(AppState::InGame)));
    }
}

/// Meshes and materials of every plant, built once.
#[derive(Resource)]
pub struct PlantAssets {
    parts: HashMap<&'static str, Vec<(Part, Handle<Mesh>, Transform)>>,
    material: Handle<StandardMaterial>,
    glossy: Handle<StandardMaterial>,
}

#[derive(Clone, Copy, PartialEq, Debug)]
enum Part {
    /// Leaves, thorns, the freckle's base: moves with the whole plant.
    Body,
    /// Popcorn Plant flower bud (pops when it fires).
    Bud,
    /// One of the Seed Ball's four husks, pivoting outward about its foot.
    Husk(u8),
    /// The seeds inside the Seed Ball.
    Core,
    /// The Choc Freckle's sprinkled top (turns while it sprays).
    Spinner,
    /// A Death Lolly's egg.
    Egg,
    /// A Death Lolly's broken shell (shown once it has gone off).
    Shell,
}

/// On the unit's view entity: which plant parts to animate.
#[derive(Component)]
pub struct PlantView {
    id: UnitId,
    root: Entity,
    parts: Vec<(Entity, Part, Transform)>,
    seq: u32,
    since_attack: f32,
    sway: f32,
}

/// Add a plant's parts under its unit view entity. Returns false when `model` is not a plant model.
pub fn spawn_plant_parts(commands: &mut Commands, view: Entity, plants: &PlantAssets, model: &str, id: UnitId) -> bool {
    let Some(list) = plants.parts.get(model) else { return false };
    let root = commands.spawn((Transform::from_scale(Vec3::splat(0.1)), Visibility::default(), Name::new("PlantRoot"))).id();
    commands.entity(view).add_child(root);
    let mut parts = Vec::new();
    for (part, mesh, rest) in list {
        let material = if matches!(part, Part::Egg | Part::Shell | Part::Spinner) { plants.glossy.clone() } else { plants.material.clone() };
        let visibility = if *part == Part::Shell { Visibility::Hidden } else { Visibility::Inherited };
        let e = commands.spawn((Mesh3d(mesh.clone()), MeshMaterial3d(material), *rest, visibility)).id();
        commands.entity(root).add_child(e);
        parts.push((e, *part, *rest));
    }
    commands.entity(view).insert(PlantView { id, root, parts, seq: 0, since_attack: 10.0, sway: (id.idx as f32 * 1.618).fract() * TAU });
    true
}

fn smooth(x: f32) -> f32 {
    let x = x.clamp(0.0, 1.0);
    x * x * (3.0 - 2.0 * x)
}

/// 0 -> 1 -> 0 over x in 0..1.
fn bump(x: f32) -> f32 {
    if (0.0..=1.0).contains(&x) { (PI * x).sin() } else { 0.0 }
}

fn animate_plants(sim: Res<GameSim>, time: Res<Time>, mut views: Query<&mut PlantView>, mut tfs: Query<&mut Transform>, mut vis: Query<&mut Visibility>) {
    let dt = time.delta_secs();
    let t = time.elapsed_secs();
    for mut v in views.iter_mut() {
        let Some(u) = sim.world.unit(v.id) else { continue };
        let def = sim.world.unit_def(u);
        let Some(p) = &def.plant else { continue };
        if u.attack_seq != v.seq {
            v.seq = u.attack_seq;
            v.since_attack = 0.0;
        }
        v.since_attack += dt;
        let a = v.since_attack;
        // growing in, from a sprout (the original's GROW frames start at a few pixels)
        let grown = if p.grow_time > 0.0 { u.age / p.grow_time } else { u.age / 0.4 };
        let g = 0.08 + 0.92 * smooth(grown);
        let hurt = u.state == UnitState::Alive && u.hp < def.hp * p.injured_below;
        let dead = match u.state {
            UnitState::Alive => 0.0,
            UnitState::Dying => (u.death_timer / 1.2).clamp(0.0, 1.0),
            UnitState::Corpse => 1.0,
        };
        // the whole plant: grow, wither when dead, sag when hurt
        let squash = (1.0 - 0.55 * smooth(dead)) * if hurt { 0.86 } else { 1.0 };
        if let Ok(mut tf) = tfs.get_mut(v.root) {
            tf.scale = Vec3::new(g, g * squash, g);
        }
        let sway = (t * 1.3 + v.sway).sin();
        for (e, part, rest) in v.parts.clone() {
            let Ok(mut tf) = tfs.get_mut(e) else { continue };
            *tf = rest;
            match part {
                Part::Body => {
                    if def.model == "plant_thorn" {
                        // the bush flexes as it fires its thorns
                        tf.scale = rest.scale * (1.0 + 0.07 * bump(a / 0.25));
                    } else if def.model == "plant_popcorn" {
                        // leaves lift as the bud pops, droop when hurt
                        let lift = 1.0 + 0.18 * bump(a / 0.45) + 0.03 * sway;
                        tf.scale = rest.scale * Vec3::new(1.0, lift * if hurt { 0.7 } else { 1.0 }, 1.0);
                    }
                }
                Part::Bud => {
                    let pop = bump(a / 0.35);
                    tf.scale = rest.scale * (1.0 + 0.4 * pop);
                    tf.rotation = rest.rotation * Quat::from_rotation_z(0.06 * sway) * Quat::from_rotation_x(0.05 * (t * 1.1 + v.sway).cos());
                    if hurt || dead > 0.0 {
                        tf.translation.y *= 0.75;
                        tf.rotation *= Quat::from_rotation_z(0.5 * dead.max(0.3));
                    }
                }
                Part::Husk(k) => {
                    // open fast, hold while the seeds fly, close again (OBPUFFBL_SPAWN)
                    let open = if a < 0.12 {
                        smooth(a / 0.12)
                    } else if a < 0.3 {
                        1.0
                    } else {
                        1.0 - smooth((a - 0.3) / 0.25)
                    };
                    let mut angle = 1.75 * open;
                    if hurt {
                        angle = angle.max(0.3 + 0.05 * k as f32);
                    }
                    angle = angle.max(1.9 * smooth(dead));
                    // the husk's local +z points away from the ball's centre; tip it outward
                    tf.rotation = rest.rotation * Quat::from_rotation_x(angle);
                }
                Part::Core => {
                    tf.scale = rest.scale * (1.0 + 0.25 * bump(a / 0.3));
                }
                Part::Spinner => {
                    tf.rotation = rest.rotation * Quat::from_rotation_y(-u.spin);
                    if u.anim == sa_sim::Anim::Attack {
                        tf.translation.y += 0.015 * (t * 18.0).sin();
                    }
                }
                Part::Egg => {
                    if let Ok(mut vv) = vis.get_mut(e) {
                        let want = if u.state == UnitState::Alive { Visibility::Inherited } else { Visibility::Hidden };
                        if *vv != want {
                            *vv = want;
                        }
                    }
                }
                Part::Shell => {
                    if let Ok(mut vv) = vis.get_mut(e) {
                        let want = if u.state == UnitState::Alive { Visibility::Hidden } else { Visibility::Inherited };
                        if *vv != want {
                            *vv = want;
                        }
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------
// geometry
// ---------------------------------------------------------------------------------------------

fn hash(a: i32, b: i32, c: u32) -> f32 {
    let mut h = (a as u32).wrapping_mul(0x9E37_79B1) ^ (b as u32).wrapping_mul(0x85EB_CA77) ^ c.wrapping_mul(0xC2B2_AE3D);
    h ^= h >> 15;
    h = h.wrapping_mul(0x2C1B_3C6D);
    h ^= h >> 12;
    h = h.wrapping_mul(0x297A_2D39);
    h ^= h >> 15;
    (h & 0x00FF_FFFF) as f32 / 16_777_216.0
}

fn mix(a: [f32; 3], b: [f32; 3], t: f32) -> [f32; 3] {
    let t = t.clamp(0.0, 1.0);
    [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
}

/// A vertex colour from an sRGB colour (as picked from the sprites) and a brightness factor.
/// Vertex colours are linear, so the colour is converted: without it every plant came out pale.
fn rgba(c: [f32; 3], k: f32) -> [f32; 4] {
    let lin = |x: f32| (x * k).clamp(0.0, 1.0).powf(2.2);
    [lin(c[0]), lin(c[1]), lin(c[2]), 1.0]
}

/// Smooth value noise in 0..1 (lumps on the Seed Ball).
fn vnoise(p: Vec3, seed: u32) -> f32 {
    let i = p.floor();
    let f = p - i;
    let s = f * f * (Vec3::splat(3.0) - 2.0 * f);
    let h = |dx: i32, dy: i32, dz: i32| hash(i.x as i32 + dx, (i.y as i32 + dy) * 131 + (i.z as i32 + dz) * 7919, seed);
    let x00 = h(0, 0, 0) + (h(1, 0, 0) - h(0, 0, 0)) * s.x;
    let x10 = h(0, 1, 0) + (h(1, 1, 0) - h(0, 1, 0)) * s.x;
    let x01 = h(0, 0, 1) + (h(1, 0, 1) - h(0, 0, 1)) * s.x;
    let x11 = h(0, 1, 1) + (h(1, 1, 1) - h(0, 1, 1)) * s.x;
    let y0 = x00 + (x10 - x00) * s.y;
    let y1 = x01 + (x11 - x01) * s.y;
    y0 + (y1 - y0) * s.z
}

/// Vertex-coloured triangle soup with smooth normals.
#[derive(Default)]
struct Geo {
    pos: Vec<Vec3>,
    col: Vec<[f32; 4]>,
    idx: Vec<u32>,
}

impl Geo {
    /// A grid of (nu + 1) x (nv + 1) vertices from `f(u, v) -> (position, colour)`, u and v in 0..=1.
    fn grid(&mut self, nu: u32, nv: u32, f: impl Fn(f32, f32) -> (Vec3, [f32; 4])) {
        let base = self.pos.len() as u32;
        for j in 0..=nv {
            for i in 0..=nu {
                let (p, c) = f(i as f32 / nu as f32, j as f32 / nv as f32);
                self.pos.push(p);
                self.col.push(c);
            }
        }
        let row = nu + 1;
        for j in 0..nv {
            for i in 0..nu {
                let a = base + j * row + i;
                let b = a + 1;
                let c = a + row;
                let d = c + 1;
                self.idx.extend_from_slice(&[a, c, b, b, c, d]);
            }
        }
    }

    /// A copy of `mesh` placed by `tf`, pushed out along its normals by `displace(local)`, coloured by
    /// `color(local position)`.
    fn add(&mut self, mesh: &Mesh, tf: Transform, displace: impl Fn(Vec3) -> f32, color: impl Fn(Vec3) -> [f32; 4]) {
        let base = self.pos.len() as u32;
        let (Some(VertexAttributeValues::Float32x3(p)), Some(VertexAttributeValues::Float32x3(n))) = (mesh.attribute(Mesh::ATTRIBUTE_POSITION), mesh.attribute(Mesh::ATTRIBUTE_NORMAL)) else {
            return;
        };
        for (p, n) in p.iter().zip(n) {
            let lp = Vec3::from_array(*p);
            let lp = lp + Vec3::from_array(*n) * displace(lp);
            self.pos.push(tf.transform_point(lp));
            self.col.push(color(lp));
        }
        match mesh.indices() {
            Some(Indices::U32(i)) => self.idx.extend(i.iter().map(|v| v + base)),
            Some(Indices::U16(i)) => self.idx.extend(i.iter().map(|v| *v as u32 + base)),
            None => self.idx.extend((0..p.len() as u32).map(|v| v + base)),
        }
    }

    fn build(self) -> Mesh {
        let mut nrm = vec![Vec3::ZERO; self.pos.len()];
        for t in self.idx.chunks_exact(3) {
            let (a, b, c) = (self.pos[t[0] as usize], self.pos[t[1] as usize], self.pos[t[2] as usize]);
            let n = (b - a).cross(c - a); // area weighted
            for &i in t {
                nrm[i as usize] += n;
            }
        }
        let nrm: Vec<[f32; 3]> = nrm.iter().map(|n| n.normalize_or(Vec3::Y).to_array()).collect();
        let mut mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default());
        mesh.insert_attribute(Mesh::ATTRIBUTE_POSITION, self.pos.iter().map(|p| p.to_array()).collect::<Vec<_>>());
        mesh.insert_attribute(Mesh::ATTRIBUTE_NORMAL, nrm);
        mesh.insert_attribute(Mesh::ATTRIBUTE_COLOR, self.col);
        mesh.insert_indices(Indices::U32(self.idx));
        mesh
    }
}

/// Horizontal unit direction at angle `a` (0 = +x, turning towards +z).
fn flat(a: f32) -> Vec3 {
    Vec3::new(a.cos(), 0.0, a.sin())
}

/// Popcorn Plant leaves (OBWHIPPL00): a rosette of broad, pointed, arching olive leaves with
/// yellow-green rims, dark at the heart.
fn popcorn_leaves(seed: u32) -> Mesh {
    let mut g = Geo::default();
    let n = 12;
    for k in 0..n {
        // seven long outer leaves, five shorter, steeper inner ones between them
        let inner = k >= 7;
        let slot = if inner { (k - 7) as f32 / 5.0 + 0.1 } else { k as f32 / 7.0 };
        let a = slot * TAU + 0.4 * (hash(k, 1, seed) - 0.5);
        let len = if inner { 0.42 + 0.1 * hash(k, 2, seed) } else { 0.74 + 0.18 * hash(k, 2, seed) };
        let wid = if inner { 0.3 } else { 0.36 + 0.08 * hash(k, 3, seed) };
        let tint = 0.88 + 0.22 * hash(k, 4, seed);
        let dir = flat(a);
        let side = Vec3::new(-dir.z, 0.0, dir.x);
        let rise = if inner { 0.44 } else { 0.34 + 0.12 * hash(k, 5, seed) };
        g.grid(16, 6, |u, v| {
            let s = v * 2.0 - 1.0; // across the leaf
            // arch: up from the heart, down to the tip (quadratic Bezier in radius/height)
            let r = (1.0 - u) * (1.0 - u) * 0.03 + 2.0 * u * (1.0 - u) * 0.32 * len + u * u * len;
            let h = (1.0 - u) * (1.0 - u) * 0.1 + 2.0 * u * (1.0 - u) * rise + u * u * 0.03;
            let w = wid * 2.1 * u.powf(0.5) * (1.0 - u).powf(0.8) * (1.0 + 0.06 * (u * 41.0 + k as f32).sin());
            // a fleshy leaf: cupped, edges up
            let p = dir * r + side * (s * w * 0.5) + Vec3::Y * (h + 0.07 * s * s * w);
            let heart = mix([0.13, 0.19, 0.03], [0.31, 0.41, 0.08], (u * 2.2).min(1.0));
            let rim = mix(heart, [0.6, 0.68, 0.19], ((s.abs() - 0.55) * 2.6).clamp(0.0, 1.0) * (0.4 + 0.6 * u));
            let c = mix(rim, [0.55, 0.64, 0.17], ((u - 0.7) * 2.5).max(0.0));
            (p, rgba(c, tint))
        });
    }
    g.build()
}

/// The Popcorn Plant's flower: a stalk with a knobbly orange head of popcorn kernels.
fn popcorn_bud(seed: u32) -> Mesh {
    let mut g = Geo::default();
    let ball = Sphere::new(1.0).mesh().ico(2).unwrap();
    // stalk
    g.grid(6, 8, |u, v| {
        let a = v * TAU;
        let r = 0.05 - 0.015 * u;
        (Vec3::new(a.cos() * r, 0.05 + u * 0.33, a.sin() * r), rgba(mix([0.12, 0.2, 0.04], [0.3, 0.42, 0.1], u), 1.0))
    });
    // kernels
    let n = 11;
    for k in 0..n {
        let (p, s) = if k == 0 {
            (Vec3::new(0.0, 0.46, 0.0), 0.12)
        } else {
            let a = k as f32 / (n - 1) as f32 * TAU + hash(k, 9, seed);
            let up = 0.38 + 0.14 * hash(k, 8, seed);
            (flat(a) * (0.08 + 0.04 * hash(k, 7, seed)) + Vec3::Y * up, 0.07 + 0.03 * hash(k, 6, seed))
        };
        let warm = hash(k, 5, seed);
        g.add(&ball, Transform::from_translation(p).with_scale(Vec3::splat(s)), |lp| 0.14 * ((lp.x * 7.0 + k as f32).sin() * (lp.z * 6.0).cos()), |lp| {
            // orange kernels, lighter where the light catches them (the sprite's highlights)
            let top = ((lp.y + 0.3) / 1.3).clamp(0.0, 1.0);
            let c = mix([0.86, 0.38, 0.06], [0.98, 0.55, 0.12], warm);
            rgba(mix(c, [1.0, 0.74, 0.34], top * top * 0.55), 1.0)
        });
    }
    g.build()
}

/// Thorn Bush (OBTHORNB00): a dark sea-urchin of long straight thorns pointing every way.
fn thorn_bush(seed: u32) -> Mesh {
    let mut g = Geo::default();
    let ball = Sphere::new(1.0).mesh().ico(2).unwrap();
    g.add(&ball, Transform::from_xyz(0.0, 0.12, 0.0).with_scale(Vec3::new(0.2, 0.15, 0.2)), |lp| 0.3 * (hash((lp.x * 9.0) as i32, (lp.z * 9.0) as i32, seed) - 0.5), |lp| {
        rgba(mix([0.04, 0.03, 0.02], [0.13, 0.1, 0.07], (lp.y + 1.0) * 0.5), 1.0)
    });
    let n = 84;
    for k in 0..n {
        // spread over a dome, more of them low and sideways as in the sprite
        let a = hash(k, 1, seed) * TAU;
        let e = (hash(k, 3, seed).powf(1.6) * 1.35).min(1.35);
        let len = 0.55 + 0.55 * hash(k, 2, seed) * (1.0 - 0.35 * e / 1.35);
        let r0 = 0.022 + 0.014 * hash(k, 5, seed);
        let dir = (flat(a) * e.cos() + Vec3::Y * e.sin()).normalize();
        let side = Vec3::new(-dir.z, 0.0, dir.x).normalize_or(Vec3::X);
        let up = dir.cross(side).normalize();
        let start = Vec3::new(0.0, 0.12, 0.0) + dir * 0.1;
        let shade = 0.85 + 0.3 * hash(k, 7, seed);
        g.grid(4, 4, |u, v| {
            let ang = v * TAU;
            let r = r0 * (1.0 - u).powf(1.2);
            let p = start + dir * (len * u) + (side * ang.cos() + up * ang.sin()) * r;
            let c = mix([0.11, 0.09, 0.07], [0.62, 0.56, 0.45], ((u - 0.3) * 1.6).clamp(0.0, 1.0));
            (p, rgba(c, shade))
        });
    }
    g.build()
}

/// One Seed Ball husk: a quarter of a lumpy dark-green ball, pale inside. Built with its foot (the
/// hinge it opens about) at the origin and the ball's centre towards -z.
fn seed_husk(k: u32, seed: u32) -> Mesh {
    let mut g = Geo::default();
    let r = 0.4;
    let bottom = 1.75_f32; // polar angle of the husk's foot (a little below the equator)
    let hinge = Vec3::new(0.0, r * bottom.cos(), r * bottom.sin());
    for inner in [false, true] {
        g.grid(12, 12, |u, v| {
            let az = (u - 0.5) * (PI * 0.5) * 1.02; // the four husks overlap a hair: no gaps
            let pol = v * bottom; // from the top down to the foot
            // the husk's direction in ball space (all four husks share one lumpy surface)
            let ball_az = az + k as f32 * PI * 0.5;
            let d = Vec3::new(pol.sin() * ball_az.sin(), pol.cos(), pol.sin() * ball_az.cos());
            let lumps = (vnoise(d * 3.2, seed) - 0.5) * 1.4 + (vnoise(d * 7.0 + 11.0, seed) - 0.5) * 0.6;
            let lump = 1.0 + 0.11 * lumps;
            let rr = r * lump * if inner { 0.92 } else { 1.0 };
            let p = Vec3::new(rr * pol.sin() * az.sin(), rr * pol.cos(), rr * pol.sin() * az.cos());
            let c = if inner {
                mix([0.42, 0.55, 0.22], [0.66, 0.7, 0.32], v)
            } else {
                // dark green, lighter on the bumps and towards the top, darkest in the creases
                let crease = 1.0 - ((u - 0.5).abs() * 2.0).powf(4.0) * 0.6;
                let t = mix([0.03, 0.2, 0.11], [0.13, 0.46, 0.27], (1.0 - v) * 0.85 + 0.15);
                let t = mix(t, [0.3, 0.62, 0.38], (lumps * 0.8 + 0.15).clamp(0.0, 0.5) * (1.0 - v * 0.7));
                let t = mix(t, [0.02, 0.12, 0.07], (-lumps * 0.9).clamp(0.0, 0.5));
                [t[0] * crease, t[1] * crease, t[2] * crease]
            };
            (p - hinge, rgba(c, 1.0))
        });
    }
    g.build()
}

/// The seed pod in the Seed Ball's heart (OBPUFFBL22: olive-yellow).
fn seed_core(seed: u32) -> Mesh {
    let mut g = Geo::default();
    let ball = Sphere::new(1.0).mesh().ico(2).unwrap();
    g.add(&ball, Transform::from_xyz(0.0, 0.2, 0.0).with_scale(Vec3::splat(0.17)), |lp| 0.08 * ((lp.x * 9.0).sin() * (lp.z * 9.0 + seed as f32).cos()), |lp| {
        rgba(mix([0.42, 0.36, 0.08], [0.78, 0.7, 0.28], (lp.y + 1.0) * 0.5), 1.0)
    });
    g.build()
}

/// A seed that has just landed: a brown kernel with a green shoot.
fn sprout(seed: u32) -> Mesh {
    let mut g = Geo::default();
    let ball = Sphere::new(1.0).mesh().ico(1).unwrap();
    g.add(&ball, Transform::from_xyz(0.0, 0.035, 0.0).with_scale(Vec3::new(0.11, 0.06, 0.075)), |_| 0.0, |lp| rgba(mix([0.3, 0.18, 0.08], [0.55, 0.38, 0.18], (lp.y + 1.0) * 0.5), 1.0));
    for k in 0..2 {
        let a = k as f32 * PI + hash(k, 1, seed);
        let dir = flat(a);
        g.grid(4, 2, |u, v| {
            let s = v * 2.0 - 1.0;
            let w = 0.06 * (PI * u).sin();
            let side = Vec3::new(-dir.z, 0.0, dir.x);
            let p = Vec3::Y * (0.06 + 0.12 * u) + dir * (0.11 * u) + side * (s * w);
            (p, rgba(mix([0.18, 0.42, 0.08], [0.45, 0.7, 0.2], u), 1.0))
        });
    }
    g.build()
}

/// Choc Freckle (FRECKLE00): a chocolate disc densely covered in hundreds-and-thousands.
fn freckle_top(seed: u32) -> Mesh {
    let mut g = Geo::default();
    let (rx, rz, h) = (0.88, 0.8, 0.16);
    let dome = |x: f32, z: f32| -> f32 {
        let d = (x / rx).powi(2) + (z / rz).powi(2);
        h * (1.0 - d).max(0.0).powf(0.4)
    };
    g.grid(32, 14, |u, v| {
        let a = u * TAU;
        let rr = v.sqrt();
        let (x, z) = (a.cos() * rx * rr, a.sin() * rz * rr);
        let p = Vec3::new(x, dome(x, z) * 0.97 + 0.01, z);
        (p, rgba(mix([0.15, 0.08, 0.04], [0.29, 0.16, 0.08], 1.0 - v * v), 1.0))
    });
    let ball = Sphere::new(1.0).mesh().ico(0).unwrap();
    // white and yellow most, as the sprite
    let colours = [[0.97, 0.96, 0.92], [0.97, 0.96, 0.92], [0.98, 0.86, 0.16], [0.98, 0.86, 0.16], [0.86, 0.12, 0.1], [0.86, 0.12, 0.1], [0.18, 0.68, 0.18], [0.18, 0.68, 0.18], [0.98, 0.52, 0.1], [0.95, 0.5, 0.65]];
    for k in 0..560 {
        let a = hash(k, 1, seed) * TAU;
        let rr = hash(k, 2, seed).sqrt() * 0.96;
        let (x, z) = (a.cos() * rx * rr, a.sin() * rz * rr);
        let s = 0.02 + 0.014 * hash(k, 3, seed);
        let c = colours[(hash(k, 4, seed) * colours.len() as f32) as usize % colours.len()];
        g.add(&ball, Transform::from_xyz(x, dome(x, z) + s * 0.4, z).with_scale(Vec3::new(s * 1.3, s * 0.8, s)).with_rotation(Quat::from_rotation_y(hash(k, 5, seed) * TAU)), |_| 0.0, |_| rgba(c, 1.0));
    }
    g.build()
}

/// Death Lolly egg (OBLOLLY*00): an egg lying on its side, with wavy stripes running tip to tip.
fn lolly_egg(base: [f32; 3], stripe: [f32; 3], broken: bool) -> Mesh {
    let mut g = Geo::default();
    let (rx, ry, rz) = (0.67, 0.3, 0.42);
    g.grid(40, 40, |u, v| {
        let lon = (u * 2.0 - 1.0) * 0.999; // along the egg, -1..1
        let ring = (1.0 - lon * lon).sqrt() * (1.0 + 0.1 * lon); // a little fatter at one end
        let phi = if broken { PI + v * PI } else { v * TAU };
        let mut p = Vec3::new(lon * rx, ry + ring * ry * phi.sin(), ring * rz * phi.cos());
        if broken {
            // only the bottom half with a jagged, torn rim: what is left after the blast
            let tear = 0.06 * (u * 47.0).sin().abs() + 0.05 * (u * 13.0 + 1.0).sin();
            let rim = 1.0 - (v - 0.5).abs() * 2.0; // 0 at the rim, 1 underneath
            p.y = p.y.min(ry * 0.9 - tear * (1.0 - rim));
            p.y -= 0.1;
        }
        // wavy bands from tip to tip, soft edged
        let band = 0.5 + 0.5 * (phi * 5.0 + 1.1 * (lon * 3.4).sin() + 0.6 * lon).sin();
        let m = ((band - 0.5) / 0.2).clamp(0.0, 1.0);
        let m = m * m * (3.0 - 2.0 * m);
        let c = mix(base, stripe, m);
        let lit = if broken { 0.75 } else { 0.82 + 0.28 * (phi.sin() * 0.5 + 0.5) };
        (p, rgba(c, lit))
    });
    g.build()
}

fn build_plant_assets(mut commands: Commands, mut meshes: ResMut<Assets<Mesh>>, mut materials: ResMut<Assets<StandardMaterial>>) {
    let material = materials.add(StandardMaterial { base_color: Color::WHITE, perceptual_roughness: 0.72, double_sided: true, cull_mode: None, ..default() });
    let glossy = materials.add(StandardMaterial { base_color: Color::WHITE, perceptual_roughness: 0.28, reflectance: 0.6, double_sided: true, cull_mode: None, ..default() });
    let mut parts: HashMap<&'static str, Vec<(Part, Handle<Mesh>, Transform)>> = HashMap::new();
    parts.insert("plant_popcorn", vec![(Part::Body, meshes.add(popcorn_leaves(3)), Transform::IDENTITY), (Part::Bud, meshes.add(popcorn_bud(5)), Transform::IDENTITY)]);
    parts.insert("plant_thorn", vec![(Part::Body, meshes.add(thorn_bush(11)), Transform::IDENTITY)]);
    let mut ball = Vec::new();
    let r = 0.4;
    let bottom = 1.75_f32;
    for k in 0..4u32 {
        // hinge on the foot of each quarter; the ball's centre sits 0.36 above the ground
        let a = k as f32 * PI * 0.5;
        let rot = Quat::from_rotation_y(-a);
        let hinge = rot * Vec3::new(0.0, r * bottom.cos(), r * bottom.sin());
        let tf = Transform::from_translation(hinge + Vec3::Y * 0.36).with_rotation(rot);
        ball.push((Part::Husk(k as u8), meshes.add(seed_husk(k, 21)), tf));
    }
    ball.push((Part::Core, meshes.add(seed_core(4)), Transform::from_xyz(0.0, 0.08, 0.0)));
    parts.insert("plant_seedball", ball);
    parts.insert("plant_seed", vec![(Part::Body, meshes.add(sprout(8)), Transform::IDENTITY)]);
    parts.insert("plant_freckle", vec![(Part::Spinner, meshes.add(freckle_top(13)), Transform::IDENTITY)]);
    for (name, base, stripe) in [
        ("plant_lolly_blue", [0.1, 0.15, 0.7], [0.42, 0.58, 1.0]),
        ("plant_lolly_orange", [0.95, 0.5, 0.08], [0.78, 0.12, 0.04]),
        ("plant_lolly_white", [0.92, 0.92, 0.88], [0.18, 0.58, 0.2]),
        ("plant_lolly_red", [0.75, 0.13, 0.13], [1.0, 0.6, 0.6]),
    ] {
        parts.insert(name, vec![(Part::Egg, meshes.add(lolly_egg(base, stripe, false)), Transform::IDENTITY), (Part::Shell, meshes.add(lolly_egg(base, stripe, true)), Transform::IDENTITY)]);
    }
    commands.insert_resource(PlantAssets { parts, material, glossy });
}
