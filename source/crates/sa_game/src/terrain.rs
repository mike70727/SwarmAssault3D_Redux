//! Plants and other map obstacles, and the navigation debug overlay (F3). The ground itself is
//! built in ground.rs.

use bevy::prelude::*;
use bevy::state::state_scoped::DespawnOnExit;

use crate::AppState;
use crate::assets::GameAssets;
use crate::controls::Controls;
use crate::ground::GroundHeight;
use crate::sim_plugin::GameSim;

#[derive(Resource, Default)]
pub struct NavDebug(pub bool);

#[derive(Component)]
pub struct TerrainEntity;

pub struct TerrainPlugin;

impl Plugin for TerrainPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<NavDebug>()
            // after the ground: obstacles stand on its height field
            .add_systems(OnEnter(AppState::InGame), spawn_obstacles.after(crate::ground::spawn_ground))
            .add_systems(Update, (toggle_nav_debug, draw_nav_debug).run_if(in_state(AppState::InGame)));
    }
}

fn spawn_obstacles(
    mut commands: Commands,
    sim: Res<GameSim>,
    assets: Res<GameAssets>,
    ground: Option<Res<GroundHeight>>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let rock = materials.add(StandardMaterial { base_color: Color::srgb(0.45, 0.42, 0.38), perceptual_roughness: 0.9, ..default() });
    let stem = materials.add(StandardMaterial { base_color: Color::srgb(0.85, 0.8, 0.6), perceptual_roughness: 0.8, ..default() });
    let cap = materials.add(StandardMaterial { base_color: Color::srgb(0.75, 0.2, 0.15), perceptual_roughness: 0.6, ..default() });
    let petal = materials.add(StandardMaterial { base_color: Color::srgb(0.9, 0.25, 0.3), perceptual_roughness: 0.6, ..default() });
    let leaf = materials.add(StandardMaterial { base_color: Color::srgb(0.2, 0.5, 0.15), perceptual_roughness: 0.8, ..default() });
    let rock_mesh = meshes.add(Sphere::new(1.0).mesh().ico(2).unwrap());
    let stem_mesh = meshes.add(Cylinder::new(0.12, 1.0).mesh().build());
    let cap_mesh = meshes.add(Sphere::new(0.5).mesh().ico(2).unwrap());
    let blade_mesh = meshes.add(Cone { radius: 0.06, height: 0.6 }.mesh().build());
    for o in &sim.world.map.obstacles {
        let y = ground.as_ref().map(|g| g.stand(o.pos.x, o.pos.y)).unwrap_or(0.0);
        let pos = Vec3::new(o.pos.x, y, o.pos.y);
        let model_ready = assets.model(&o.kind).is_some_and(|m| m.ready && m.scene.is_some());
        let mut e = commands.spawn((TerrainEntity, DespawnOnExit(AppState::InGame), Name::new(format!("Obstacle {}", o.kind)), Transform::from_translation(pos).with_rotation(Quat::from_rotation_y(o.yaw)).with_scale(Vec3::splat(o.scale)), Visibility::default()));
        if model_ready {
            let scene = assets.model(&o.kind).unwrap().scene.clone().unwrap();
            e.with_children(|p| {
                p.spawn(WorldAssetRoot(scene));
            });
            continue;
        }
        match o.kind.as_str() {
            k if k.starts_with("rock") => {
                let r = o.radius;
                e.with_children(|p| {
                    p.spawn((Mesh3d(rock_mesh.clone()), MeshMaterial3d(rock.clone()), Transform::from_xyz(0.0, r * 0.35, 0.0).with_scale(Vec3::new(r * 1.1, r * 0.7, r * 0.9))));
                    p.spawn((Mesh3d(rock_mesh.clone()), MeshMaterial3d(rock.clone()), Transform::from_xyz(r * 0.5, r * 0.25, -r * 0.3).with_scale(Vec3::new(r * 0.6, r * 0.45, r * 0.55))));
                });
            }
            "mushroom" => {
                e.with_children(|p| {
                    p.spawn((Mesh3d(stem_mesh.clone()), MeshMaterial3d(stem.clone()), Transform::from_xyz(0.0, 0.5, 0.0).with_scale(Vec3::new(1.6, 1.0, 1.6))));
                    p.spawn((Mesh3d(cap_mesh.clone()), MeshMaterial3d(cap.clone()), Transform::from_xyz(0.0, 1.0, 0.0).with_scale(Vec3::new(1.6, 0.8, 1.6))));
                });
            }
            "flower" => {
                e.with_children(|p| {
                    p.spawn((Mesh3d(stem_mesh.clone()), MeshMaterial3d(leaf.clone()), Transform::from_xyz(0.0, 0.6, 0.0).with_scale(Vec3::new(0.5, 1.2, 0.5))));
                    for i in 0..5 {
                        let a = i as f32 / 5.0 * std::f32::consts::TAU;
                        p.spawn((Mesh3d(cap_mesh.clone()), MeshMaterial3d(petal.clone()), Transform::from_xyz(a.cos() * 0.35, 1.25, a.sin() * 0.35).with_scale(Vec3::new(0.5, 0.25, 0.5))));
                    }
                    p.spawn((Mesh3d(cap_mesh.clone()), MeshMaterial3d(stem.clone()), Transform::from_xyz(0.0, 1.3, 0.0).with_scale(Vec3::splat(0.35))));
                });
            }
            _ => {
                // grass tuft: a few leaning blades
                e.with_children(|p| {
                    for i in 0..7 {
                        let a = i as f32 * 0.9;
                        let lean = Quat::from_rotation_x(0.35 * (i as f32 * 1.7).sin()) * Quat::from_rotation_z(0.35 * (i as f32 * 2.3).cos());
                        p.spawn((Mesh3d(blade_mesh.clone()), MeshMaterial3d(leaf.clone()), Transform::from_xyz(a.cos() * 0.15, 0.3, a.sin() * 0.15).with_rotation(lean)));
                    }
                });
            }
        }
    }
}

fn toggle_nav_debug(keys: Res<ButtonInput<KeyCode>>, controls: Res<Controls>, mut dbg: ResMut<NavDebug>) {
    if controls.just_pressed(&keys, "debug_nav") {
        dbg.0 = !dbg.0;
    }
}

fn draw_nav_debug(dbg: Res<NavDebug>, sim: Res<GameSim>, mut gizmos: Gizmos) {
    if !dbg.0 {
        return;
    }
    for c in sim.world.grid.blocked_cells() {
        let p = Vec3::new(c.x as f32 + 0.5, 0.05, c.y as f32 + 0.5);
        gizmos.rect(Isometry3d::new(p, Quat::from_rotation_x(-std::f32::consts::FRAC_PI_2)), Vec2::splat(0.9), Color::srgba(1.0, 0.2, 0.2, 0.6));
    }
    for u in sim.world.living_units() {
        if u.path_next < u.path.len() {
            let mut pts = vec![Vec3::new(u.pos.x, 0.1, u.pos.y)];
            pts.extend(u.path[u.path_next..].iter().map(|p| Vec3::new(p.x, 0.1, p.y)));
            gizmos.linestrip(pts, Color::srgba(0.2, 0.9, 1.0, 0.8));
        }
    }
}
