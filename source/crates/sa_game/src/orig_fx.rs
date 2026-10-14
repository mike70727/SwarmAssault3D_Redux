//! The original game's explosions and projectiles (Game.ANI animations of Game.DDF pictures) in
//! the 3-D world: explosions are camera-facing sprites standing on the impact point, projectiles
//! are flat sprites flying along their heading (as the original drew them from above). Used
//! instead of the game's own impact spheres and projectile beads when the original is found.

use std::collections::HashMap;

use bevy::asset::RenderAssetUsages;
use bevy::image::ImageSampler;
use bevy::light::NotShadowCaster;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};
use bevy::state::state_scoped::DespawnOnExit;
use sa_sim::SimEvent;

use crate::AppState;
use crate::camera::MainCamera;
use crate::ground::GroundHeight;
use crate::original::{Original, Rgba};
use crate::sim_plugin::GameSim;

/// Original pixels per map cell.
const PX: f32 = 24.0;

/// One frame of an effect: its material, its size and its anchor offset in world units.
#[derive(Clone)]
struct Frame {
    material: Handle<StandardMaterial>,
    size: Vec2,
    /// offset of the picture's centre from the animation origin (x right, y down in pixels / 24)
    centre: Vec2,
}

#[derive(Clone)]
struct Anim {
    frames: Vec<Frame>,
    seconds_per_frame: f32,
}

#[derive(Resource)]
pub struct OrigFx {
    anims: HashMap<&'static str, Anim>,
    quad: Handle<Mesh>,
}

impl OrigFx {
    pub fn has(&self, name: &str) -> bool {
        self.anims.contains_key(name)
    }
}

/// Explosion animations (Game.ANI names) and their seconds per frame.
const EXPLOSIONS: &[(&str, f32)] = &[
    ("ExplosionA", 0.04),
    ("ExplosionB", 0.04),
    ("ExplosionC", 0.045),
    ("ExplosionD", 0.04),
    ("ExplosionE", 0.045),
    ("ExplosionF", 0.08),
    ("ExplosionG", 0.04),
    ("ExplosionX", 0.07),
];

/// The original drew its effects over a black background with black as the colour key: the fire
/// keeps its colours, its opacity follows its brightness so the dark fringes fade into the ground.
fn glow_alpha(mut p: Rgba) -> Rgba {
    for px in p.px.chunks_exact_mut(4) {
        let m = px[0].max(px[1]).max(px[2]) as f32 / 255.0;
        px[3] = ((m * 2.2).min(1.0) * px[3] as f32) as u8;
    }
    p
}

/// Pure black made transparent (projectile sprites).
fn black_key(mut p: Rgba) -> Rgba {
    for px in p.px.chunks_exact_mut(4) {
        if px[0] < 8 && px[1] < 8 && px[2] < 8 {
            px[3] = 0;
        }
    }
    p
}

/// Projectile animations (Game.ANI names).
const PROJECTILES: &[(&str, f32)] = &[
    ("WEAPON_GRENADE", 0.08),
    ("WEAPON_ROCKET", 0.05),
    ("WEAPON_MISSILE", 0.05),
    ("WEAPON_SPEAR", 0.1),
    ("WEAPON_STAR", 0.05),
    ("WEAPON_ARROW", 0.1),
    ("WEAPON_SONIC", 0.1),
    ("WEAPON_SMALL", 0.1),
    ("WEAPON_MEDIUM", 0.1),
    ("WEAPON_CANNON", 0.1),
    ("WEAPON_BRAKEBOMB", 0.08),
    ("WEAPON_BOUNCEBOMB", 0.08),
    ("WEAPON_GOBSTOPPER", 0.08),
    ("WEAPON_PUFFBALL", 0.1),
];

/// The explosion of a simulation effect id.
fn explosion_for(effect: &str, variant: u32) -> &'static str {
    match effect {
        "explosion_big" => {
            if variant % 2 == 0 {
                "ExplosionA"
            } else {
                "ExplosionG"
            }
        }
        "explosion_medium" => "ExplosionD",
        "explosion_shrapnel" => "ExplosionB",
        "paralyze" => "ExplosionF",
        "colony_explode" => "ExplosionC",
        "bite" => "ExplosionX",
        _ => "ExplosionE",
    }
}

/// The projectile sprite of a weapon id.
fn projectile_for(weapon: &str) -> Option<&'static str> {
    Some(match weapon {
        "ant_grenade" | "pirate_grenade" => "WEAPON_GRENADE",
        "ant_rocket" => "WEAPON_ROCKET",
        "spider_missile" => "WEAPON_MISSILE",
        "scorpion_spear" | "colony_scorpion_spear" => "WEAPON_SPEAR",
        "scorpion_star" => "WEAPON_STAR",
        "wasp_paralysis" => "WEAPON_ARROW",
        "wasp_sonic" => "WEAPON_SONIC",
        "wasp_mg" | "colony_wasp_mg" => "WEAPON_SMALL",
        "beetle_shrapnel" | "popcorn" => "WEAPON_MEDIUM",
        "beetle_cannon" | "colony_beetle_cannon" => "WEAPON_CANNON",
        "dragonfly_bomb" => "WEAPON_BRAKEBOMB",
        "fly_bomb" => "WEAPON_BOUNCEBOMB",
        "machine_gobstopper" => "WEAPON_GOBSTOPPER",
        "moth_puff" => "WEAPON_PUFFBALL",
        _ => return None,
    })
}

pub struct OrigFxPlugin;

impl Plugin for OrigFxPlugin {
    fn build(&self, app: &mut App) {
        let original = app.world().resource::<Original>().clone();
        let Some(orig) = original.get() else { return };
        let mut anims = HashMap::new();
        let mut count = 0;
        {
            let world = app.world_mut();
            let mut frames_of = |name: &str| -> Vec<(Rgba, IVec2)> { orig.animation(name) };
            let mut built: Vec<(&'static str, f32, Vec<(Rgba, IVec2)>)> = Vec::new();
            for (name, spf) in EXPLOSIONS.iter().chain(PROJECTILES) {
                let explosion = name.starts_with("Explosion");
                let f: Vec<(Rgba, IVec2)> = frames_of(name).into_iter().map(|(p, o)| (if explosion { glow_alpha(p) } else { black_key(p) }, o)).collect();
                if !f.is_empty() {
                    built.push((name, *spf, f));
                }
            }
            let mut images = Vec::new();
            {
                let mut image_assets = world.resource_mut::<Assets<Image>>();
                for (_, _, frames) in &built {
                    let mut hs = Vec::new();
                    for (pic, _) in frames {
                        let mut img = Image::new(
                            Extent3d { width: pic.w, height: pic.h, depth_or_array_layers: 1 },
                            TextureDimension::D2,
                            pic.px.clone(),
                            TextureFormat::Rgba8UnormSrgb,
                            RenderAssetUsages::RENDER_WORLD,
                        );
                        img.sampler = ImageSampler::linear();
                        hs.push(image_assets.add(img));
                    }
                    images.push(hs);
                }
            }
            let mut materials = world.resource_mut::<Assets<StandardMaterial>>();
            for ((name, spf, frames), hs) in built.into_iter().zip(images) {
                let frames = frames
                    .iter()
                    .zip(hs)
                    .map(|((pic, off), h)| {
                        count += 1;
                        Frame {
                            material: materials.add(StandardMaterial {
                                base_color_texture: Some(h),
                                unlit: true,
                                alpha_mode: AlphaMode::Blend,
                                double_sided: true,
                                cull_mode: None,
                                ..default()
                            }),
                            size: Vec2::new(pic.w as f32, pic.h as f32) / PX,
                            centre: (Vec2::new(off.x as f32, off.y as f32) + Vec2::new(pic.w as f32, pic.h as f32) * 0.5) / PX,
                        }
                    })
                    .collect();
                anims.insert(name, Anim { frames, seconds_per_frame: spf });
            }
            let quad = world.resource_mut::<Assets<Mesh>>().add(Rectangle::new(1.0, 1.0).mesh().build());
            world.insert_resource(OrigFx { anims, quad });
        }
        info!("original effects loaded: {count} frames");
        app.add_systems(Update, (spawn_explosions, sync_projectile_sprites, animate_sprites).chain().run_if(in_state(AppState::InGame)));
    }
}

/// A playing explosion: a camera-facing sprite on the ground.
#[derive(Component)]
struct Explosion {
    anim: &'static str,
    t: f32,
    origin: Vec3,
}

/// A projectile drawn with the original sprite, lying flat along its heading.
#[derive(Component)]
pub struct ProjectileSprite {
    id: u32,
    anim: &'static str,
    t: f32,
}

fn spawn_explosions(mut commands: Commands, sim: Res<GameSim>, fx: Res<OrigFx>, ground: Option<Res<GroundHeight>>, mut n: Local<u32>) {
    let gy = |p: Vec2| ground.as_ref().map(|g| g.stand(p.x, p.y)).unwrap_or(0.0);
    for e in &sim.events {
        let (pos, name) = match e {
            SimEvent::Impact { pos, effect, .. } => {
                *n = n.wrapping_add(1);
                (*pos, explosion_for(effect, *n))
            }
            SimEvent::ColonyScattered(cid) => match sim.world.colonies.get(*cid as usize) {
                Some(c) => (c.pos, "ExplosionC"),
                None => continue,
            },
            _ => continue,
        };
        let Some(anim) = fx.anims.get(name) else {
            debug!("no original animation {name}");
            continue;
        };
        if std::env::var("SA_FX_DEBUG").is_ok() {
            info!("explosion {name} at {pos:?} ground {:.2}", gy(pos));
        }
        let first = &anim.frames[0];
        commands.spawn((
            Explosion { anim: name, t: 0.0, origin: Vec3::new(pos.x, gy(pos), pos.y) },
            DespawnOnExit(AppState::InGame),
            NotShadowCaster,
            Mesh3d(fx.quad.clone()),
            MeshMaterial3d(first.material.clone()),
            Transform::from_xyz(pos.x, gy(pos) + 0.3, pos.y).with_scale(first.size.extend(1.0)),
            Name::new("Explosion"),
        ));
    }
}

/// Projectiles with an original sprite get one (the game's own bead stays hidden under it).
fn sync_projectile_sprites(mut commands: Commands, sim: Res<GameSim>, fx: Res<OrigFx>, mut views: Query<(&crate::views::ProjectileView, &mut Visibility), Without<ProjectileSprite>>, sprites: Query<(Entity, &ProjectileSprite)>, mut known: Local<std::collections::HashSet<u32>>) {
    for p in &sim.world.projectiles {
        if !p.alive || known.contains(&p.id) {
            continue;
        }
        let Some(weapon_id) = sim.world.defs.weapon_ids.get(p.weapon as usize) else { continue };
        let Some(name) = projectile_for(weapon_id) else { continue };
        let Some(anim) = fx.anims.get(name) else { continue };
        known.insert(p.id);
        commands.spawn((
            ProjectileSprite { id: p.id, anim: name, t: 0.0 },
            DespawnOnExit(AppState::InGame),
            NotShadowCaster,
            Mesh3d(fx.quad.clone()),
            MeshMaterial3d(anim.frames[0].material.clone()),
            Transform::from_xyz(p.pos.x, p.height + 0.1, p.pos.y),
            Name::new("ProjectileSprite"),
        ));
    }
    // hide the beads the sprites replace
    for (view, mut vis) in &mut views {
        if known.contains(&view.0) && *vis != Visibility::Hidden {
            *vis = Visibility::Hidden;
        }
    }
    // drop sprites whose projectile is gone
    for (e, s) in &sprites {
        if !sim.world.projectiles.iter().any(|p| p.alive && p.id == s.id) {
            commands.entity(e).despawn();
            known.remove(&s.id);
        }
    }
}

#[allow(clippy::type_complexity)]
fn animate_sprites(
    mut commands: Commands,
    time: Res<Time>,
    sim: Res<GameSim>,
    fx: Res<OrigFx>,
    ground: Option<Res<GroundHeight>>,
    cameras: Query<&GlobalTransform, With<MainCamera>>,
    mut explosions: Query<(Entity, &mut Explosion, &mut Transform, &mut MeshMaterial3d<StandardMaterial>), Without<ProjectileSprite>>,
    mut projectiles: Query<(&mut ProjectileSprite, &mut Transform, &mut MeshMaterial3d<StandardMaterial>), Without<Explosion>>,
) {
    let dt = time.delta_secs();
    let Ok(cam) = cameras.single() else { return };
    let (_, cam_rot, cam_pos) = cam.to_scale_rotation_translation();
    let right = cam_rot * Vec3::X;
    let up = cam_rot * Vec3::Y;
    for (e, mut ex, mut tf, mut mat) in &mut explosions {
        let Some(anim) = fx.anims.get(ex.anim) else { continue };
        ex.t += dt;
        let i = (ex.t / anim.seconds_per_frame) as usize;
        if i >= anim.frames.len() {
            commands.entity(e).despawn();
            continue;
        }
        let f = &anim.frames[i];
        if mat.0 != f.material {
            mat.0 = f.material.clone();
        }
        // stand the picture on the impact point facing the camera; pull it towards the camera so
        // the ground does not cut its lower half
        let to_cam = (cam_pos - ex.origin).normalize_or_zero();
        tf.translation = ex.origin + right * f.centre.x - up * f.centre.y + to_cam * 0.6;
        tf.rotation = cam_rot;
        tf.scale = f.size.extend(1.0);
    }
    let gy = |p: Vec2| ground.as_ref().map(|g| g.stand(p.x, p.y)).unwrap_or(0.0);
    for (mut s, mut tf, mut mat) in &mut projectiles {
        let Some(p) = sim.world.projectiles.iter().find(|p| p.id == s.id) else { continue };
        let Some(anim) = fx.anims.get(s.anim) else { continue };
        s.t += dt;
        let f = &anim.frames[(s.t / anim.seconds_per_frame) as usize % anim.frames.len()];
        if mat.0 != f.material {
            mat.0 = f.material.clone();
        }
        // flat on the ground plane, the picture's top pointing along the heading
        tf.translation = Vec3::new(p.pos.x, gy(p.pos) + p.height.max(0.05) + 0.05, p.pos.y);
        tf.rotation = Quat::from_rotation_y(p.heading) * Quat::from_rotation_x(-std::f32::consts::FRAC_PI_2) * Quat::from_rotation_z(std::f32::consts::PI);
        tf.scale = f.size.extend(1.0);
    }
}
