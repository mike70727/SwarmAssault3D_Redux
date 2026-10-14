//! Top-down RTS camera: pan (keys, edge, middle drag), zoom (wheel), rotate (Q/E).

use std::f32::consts::FRAC_PI_4;

use bevy::input::mouse::{AccumulatedMouseMotion, AccumulatedMouseScroll};
use bevy::core_pipeline::tonemapping::Tonemapping;
use bevy::light::CascadeShadowConfigBuilder;
use bevy::prelude::*;
use bevy::state::state_scoped::DespawnOnExit;
use bevy::window::PrimaryWindow;

use crate::AppState;
use crate::settings::Settings;
use crate::controls::Controls;
use crate::sim_plugin::GameSim;

#[derive(Resource, Debug, Clone)]
pub struct RtsCamera {
    pub focus: Vec3,
    pub yaw: f32,
    pub pitch: f32,
    pub distance: f32,
    pub min_distance: f32,
    pub max_distance: f32,
    pub map_size: Vec2,
}

impl RtsCamera {
    pub fn position(&self) -> Vec3 {
        let dir = Vec3::new(self.yaw.sin() * self.pitch.cos(), self.pitch.sin(), self.yaw.cos() * self.pitch.cos());
        self.focus + dir * self.distance
    }
}

#[derive(Component)]
pub struct MainCamera;

/// Vertical field of view of the game camera.
pub const CAMERA_FOV: f32 = 45.0 * std::f32::consts::PI / 180.0;

pub struct CameraPlugin;

impl Plugin for CameraPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(AppState::InGame), setup_camera)
            .add_systems(Update, (camera_input.run_if(|c: Res<crate::console::ConsoleState>| !c.open), apply_camera).chain().run_if(in_state(AppState::InGame)));
    }
}

fn setup_camera(mut commands: Commands, sim: Res<GameSim>, settings: Res<Settings>, cli: Res<crate::CliOptions>) {
    let size = sim.world.grid.size();
    // start looking at the human team's first colony (or the --focus point)
    let team = sim.human_team();
    let focus = cli
        .focus
        .map(|(x, y)| Vec2::new(x, y - 4.0))
        .or_else(|| sim.world.map.camera.map(|c| Vec2::new(c.x, c.y - 4.0)))
        .or_else(|| sim.world.colonies.iter().find(|c| c.team == team).map(|c| c.pos))
        .unwrap_or(size * 0.5);
    let cam = RtsCamera {
        focus: Vec3::new(focus.x, 0.0, focus.y + 4.0),
        yaw: 0.0,
        pitch: 58f32.to_radians(),
        distance: cli.zoom.unwrap_or(26.0),
        min_distance: 8.0,
        max_distance: 70.0,
        map_size: size,
    };
    commands.spawn((
        MainCamera,
        DespawnOnExit(AppState::InGame),
        Camera3d::default(),
        Projection::Perspective(PerspectiveProjection { fov: CAMERA_FOV, near: 0.1, far: 400.0, ..default() }),
        Transform::from_translation(cam.position()).looking_at(cam.focus, Vec3::Y),
        settings.msaa(),
        // ACES keeps the team colours saturated (the default TonyMcMapface washes them out)
        Tonemapping::AcesFitted,
    ));
    commands.insert_resource(cam);
    commands.spawn((
        DespawnOnExit(AppState::InGame),
        DirectionalLight { illuminance: 5500.0, shadow_maps_enabled: settings.shadows, ..default() },
        CascadeShadowConfigBuilder { num_cascades: settings.shadow_cascades.clamp(1, 4), first_cascade_far_bound: 20.0, maximum_distance: settings.shadow_distance.max(20.0), ..default() }.build(),
        Transform::from_rotation(Quat::from_euler(EulerRot::YXZ, -0.6, -1.0, 0.0)),
    ));
    commands.insert_resource(GlobalAmbientLight { color: Color::srgb(0.8, 0.85, 1.0), brightness: 220.0, ..default() });
}

fn camera_input(
    mut cam: ResMut<RtsCamera>,
    keys: Res<ButtonInput<KeyCode>>,
    buttons: Res<ButtonInput<MouseButton>>,
    scroll: Res<AccumulatedMouseScroll>,
    motion: Res<AccumulatedMouseMotion>,
    controls: Res<Controls>,
    time: Res<Time>,
    windows: Query<&Window, With<PrimaryWindow>>,
) {
    let dt = time.delta_secs();
    let mut pan = Vec2::ZERO; // x = right, y = forward (screen up)
    if controls.pressed(&keys, "pan_up") {
        pan.y += 1.0;
    }
    if controls.pressed(&keys, "pan_down") {
        pan.y -= 1.0;
    }
    if controls.pressed(&keys, "pan_left") {
        pan.x -= 1.0;
    }
    if controls.pressed(&keys, "pan_right") {
        pan.x += 1.0;
    }
    if controls.edge_pan
        && let Ok(window) = windows.single()
        && let Some(c) = window.cursor_position()
    {
        let s = window.size();
        let m = controls.edge_pan_margin;
        if c.x <= m {
            pan.x -= 1.0;
        }
        // the map view ends where the sidebar starts
        let right_edge = s.x - crate::hud::SIDEBAR_WIDTH;
        if c.x >= right_edge - m && c.x < right_edge + m {
            pan.x += 1.0;
        }
        if c.y <= m {
            pan.y += 1.0;
        }
        if c.y >= s.y - m {
            pan.y -= 1.0;
        }
    }
    // screen up on the ground, and screen right (forward x up): panning right moves the view right
    let forward = Vec3::new(-cam.yaw.sin(), 0.0, -cam.yaw.cos());
    let right = Vec3::new(-forward.z, 0.0, forward.x);
    if buttons.pressed(MouseButton::Middle)
        && motion.delta != Vec2::ZERO
        && let Ok(window) = windows.single()
    {
        // middle drag grabs the ground: the point under the cursor follows the cursor (screen-down
        // motion covers more ground because of the camera pitch)
        let units_per_px = 2.0 * cam.distance * (CAMERA_FOV * 0.5).tan() / window.height().max(1.0);
        let depth = cam.pitch.sin().max(0.3);
        cam.focus += (-right * motion.delta.x + forward * motion.delta.y / depth) * units_per_px;
    }
    if pan != Vec2::ZERO {
        let speed = controls.pan_speed * (cam.distance / 26.0).clamp(0.4, 3.0) * dt;
        cam.focus += (right * pan.x + forward * pan.y) * speed;
    }
    if controls.pressed(&keys, "rotate_left") {
        cam.yaw += controls.rotate_speed * dt;
    }
    if controls.pressed(&keys, "rotate_right") {
        cam.yaw -= controls.rotate_speed * dt;
    }
    let mut zoom = 0.0;
    if scroll.delta.y != 0.0 {
        zoom -= scroll.delta.y.signum() * 0.12 * controls.zoom_speed * if controls.invert_zoom { -1.0 } else { 1.0 };
    }
    if controls.pressed(&keys, "zoom_in") {
        zoom -= 1.5 * dt;
    }
    if controls.pressed(&keys, "zoom_out") {
        zoom += 1.5 * dt;
    }
    if zoom != 0.0 {
        cam.distance = (cam.distance * (1.0 + zoom)).clamp(cam.min_distance, cam.max_distance);
        // steeper when zoomed out, flatter when close
        let t = (cam.distance - cam.min_distance) / (cam.max_distance - cam.min_distance);
        cam.pitch = (FRAC_PI_4 + t * 0.55).clamp(0.6, 1.5);
    }
    if controls.just_pressed(&keys, "center_camera") {
        cam.focus = Vec3::new(cam.map_size.x * 0.5, 0.0, cam.map_size.y * 0.5);
    }
    let size = cam.map_size;
    cam.focus.x = cam.focus.x.clamp(0.0, size.x);
    cam.focus.z = cam.focus.z.clamp(0.0, size.y);
    cam.focus.y = 0.0;
}

fn apply_camera(cam: Res<RtsCamera>, mut q: Query<&mut Transform, With<MainCamera>>) {
    for mut t in q.iter_mut() {
        *t = Transform::from_translation(cam.position()).looking_at(cam.focus, Vec3::Y);
    }
}

/// Intersect the cursor ray with the ground plane (y = 0). Returns sim coordinates (x, y=z).
pub fn cursor_ground_point(camera: &Camera, cam_tf: &GlobalTransform, cursor: Vec2) -> Option<Vec2> {
    let ray = camera.viewport_to_world(cam_tf, cursor).ok()?;
    let dir: Vec3 = ray.direction.into();
    if dir.y.abs() < 1e-5 {
        return None;
    }
    let t = -ray.origin.y / dir.y;
    if t < 0.0 {
        return None;
    }
    let p = ray.origin + dir * t;
    Some(Vec2::new(p.x, p.z))
}
