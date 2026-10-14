//! Ground mesh with per-cell terrain colours, procedural environment objects and a nav debug overlay.

use bevy::asset::RenderAssetUsages;
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::prelude::*;
use bevy::state::state_scoped::DespawnOnExit;
use sa_sim::TerrainKind;

use crate::AppState;
use crate::assets::GameAssets;
use crate::controls::Controls;
use crate::sim_plugin::GameSim;

#[derive(Resource, Default)]
pub struct NavDebug(pub bool);

#[derive(Component)]
pub struct TerrainEntity;

pub struct TerrainPlugin;

impl Plugin for TerrainPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<NavDebug>()
            .add_systems(OnEnter(AppState::InGame), (spawn_ground, spawn_obstacles))
            .add_systems(Update, (toggle_nav_debug, draw_nav_debug).run_if(in_state(AppState::InGame)));
    }
}

fn hash2(x: i32, y: i32) -> f32 {
    let mut h = (x as u32).wrapping_mul(374761393) ^ (y as u32).wrapping_mul(668265263);
    h = (h ^ (h >> 13)).wrapping_mul(1274126177);
    ((h ^ (h >> 16)) & 0xffff) as f32 / 65535.0
}

fn terrain_color(kind: TerrainKind, n: f32, tileset: &str) -> [f32; 4] {
    // base palettes per tileset (the "normal" one is the original green grass; desert, swamp and
    // candy follow the OpenSA minimap colours of those tilesets)
    let c = match (tileset, kind) {
        ("desert", TerrainKind::Clear) => [0.72 + 0.08 * n, 0.58 + 0.08 * n, 0.34 + 0.05 * n],
        ("desert", TerrainKind::Rock) => [0.50 + 0.1 * n, 0.46 + 0.08 * n, 0.42 + 0.05 * n],
        ("desert", TerrainKind::Vegetation) => [0.40 + 0.06 * n, 0.30 + 0.06 * n, 0.16 + 0.04 * n],
        ("desert", TerrainKind::Water) => [0.26 + 0.03 * n, 0.22 + 0.03 * n, 0.20],
        ("swamp", TerrainKind::Clear) => [0.34 + 0.06 * n, 0.38 + 0.08 * n, 0.22 + 0.04 * n],
        ("swamp", TerrainKind::Rock) => [0.26 + 0.06 * n, 0.32 + 0.06 * n, 0.18 + 0.04 * n],
        ("swamp", TerrainKind::Vegetation) => [0.18 + 0.04 * n, 0.20 + 0.05 * n, 0.36 + 0.06 * n],
        ("swamp", TerrainKind::Water) => [0.14, 0.30 + 0.05 * n, 0.22 + 0.05 * n],
        ("candy", TerrainKind::Clear) => [0.74 + 0.06 * n, 0.64 + 0.06 * n, 0.60 + 0.06 * n],
        ("candy", TerrainKind::Rock) => [0.66 + 0.08 * n, 0.52 + 0.06 * n, 0.44 + 0.05 * n],
        ("candy", TerrainKind::Vegetation) => [0.56 + 0.08 * n, 0.14 + 0.04 * n, 0.16 + 0.04 * n],
        ("candy", TerrainKind::Water) => [0.42 + 0.04 * n, 0.36 + 0.04 * n, 0.50 + 0.05 * n],
        (_, TerrainKind::Clear) => [0.36 + 0.08 * n, 0.56 + 0.1 * n, 0.22 + 0.05 * n],
        (_, TerrainKind::Rock) => [0.52 + 0.1 * n, 0.49 + 0.08 * n, 0.42 + 0.05 * n],
        (_, TerrainKind::Vegetation) => [0.2 + 0.06 * n, 0.42 + 0.08 * n, 0.14 + 0.04 * n],
        (_, TerrainKind::Water) => [0.2, 0.4 + 0.05 * n, 0.68 + 0.08 * n],
    };
    [c[0], c[1], c[2], 1.0]
}

fn spawn_ground(mut commands: Commands, sim: Res<GameSim>, mut meshes: ResMut<Assets<Mesh>>, mut materials: ResMut<Assets<StandardMaterial>>) {
    let grid = &sim.world.grid;
    let (w, h) = (grid.w, grid.h);
    let mut positions = Vec::with_capacity((w * h * 4) as usize);
    let mut normals = Vec::with_capacity((w * h * 4) as usize);
    let mut uvs = Vec::with_capacity((w * h * 4) as usize);
    let mut colors = Vec::with_capacity((w * h * 4) as usize);
    let mut indices = Vec::with_capacity((w * h * 6) as usize);
    for y in 0..h {
        for x in 0..w {
            let kind = grid.terrain_at(Vec2::new(x as f32 + 0.5, y as f32 + 0.5));
            let n = hash2(x, y);
            let c = terrain_color(kind, n, &sim.world.map.tileset);
            let base = positions.len() as u32;
            let (fx, fy) = (x as f32, y as f32);
            // slight height noise keeps the ground from looking flat-shaded
            let z0 = 0.0;
            for (px, py) in [(fx, fy), (fx + 1.0, fy), (fx + 1.0, fy + 1.0), (fx, fy + 1.0)] {
                positions.push([px, z0, py]);
                normals.push([0.0, 1.0, 0.0]);
                uvs.push([px / w as f32, py / h as f32]);
                colors.push(c);
            }
            indices.extend_from_slice(&[base, base + 2, base + 1, base, base + 3, base + 2]);
        }
    }
    let mut mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default());
    mesh.insert_attribute(Mesh::ATTRIBUTE_POSITION, positions);
    mesh.insert_attribute(Mesh::ATTRIBUTE_NORMAL, normals);
    mesh.insert_attribute(Mesh::ATTRIBUTE_UV_0, uvs);
    mesh.insert_attribute(Mesh::ATTRIBUTE_COLOR, colors);
    mesh.insert_indices(Indices::U32(indices));
    let mat = materials.add(StandardMaterial { base_color: Color::WHITE, perceptual_roughness: 0.95, ..default() });
    commands.spawn((TerrainEntity, DespawnOnExit(AppState::InGame), Name::new("Ground"), Mesh3d(meshes.add(mesh)), MeshMaterial3d(mat)));
    // dark border skirt outside the map
    let skirt = materials.add(StandardMaterial { base_color: Color::srgb(0.1, 0.12, 0.08), perceptual_roughness: 1.0, ..default() });
    let big = meshes.add(Plane3d::default().mesh().size(w as f32 + 400.0, h as f32 + 400.0));
    commands.spawn((TerrainEntity, DespawnOnExit(AppState::InGame), Name::new("Skirt"), Mesh3d(big), MeshMaterial3d(skirt), Transform::from_xyz(w as f32 * 0.5, -0.05, h as f32 * 0.5)));
}

fn spawn_obstacles(mut commands: Commands, sim: Res<GameSim>, assets: Res<GameAssets>, mut meshes: ResMut<Assets<Mesh>>, mut materials: ResMut<Assets<StandardMaterial>>) {
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
        let pos = Vec3::new(o.pos.x, 0.0, o.pos.y);
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
