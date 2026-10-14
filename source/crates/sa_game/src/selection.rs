//! Mouse selection (click, double click, drag box, shift-add), orders (move, attack, attack-move,
//! stop), colony production hotkeys and selection decorations.

use bevy::prelude::*;
use bevy::state::state_scoped::DespawnOnExit;
use bevy::window::PrimaryWindow;
use sa_sim::{Order, Target, UnitId};

use crate::AppState;
use crate::camera::{MainCamera, cursor_ground_point};
use crate::controls::Controls;
use crate::sim_plugin::{GameSim, PendingOrders};

#[derive(Resource, Default)]
pub struct Selection {
    pub units: Vec<UnitId>,
    pub colony: Option<u32>,
}

#[derive(Resource, Default)]
pub struct DragState {
    pub start: Option<Vec2>,
    pub current: Vec2,
    pub dragging: bool,
    pub last_click: LastClick,
}

/// Two clicks on bugs of the same kind this close in time (seconds, real time) and place (pixels)
/// are a double click: as in the original game, it selects every bug of that kind on the screen.
const DOUBLE_CLICK_S: f32 = 0.45;
const DOUBLE_CLICK_PX: f32 = 8.0;

/// The last click on one of the player's bugs: real time, cursor position, unit kind.
#[derive(Default)]
pub struct LastClick(Option<(f32, Vec2, u16)>);

impl LastClick {
    /// Record a click on a bug of `kind`; true when it completes a double click (a third click then
    /// starts a new pair).
    fn click(&mut self, now: f32, at: Vec2, kind: u16) -> bool {
        let double = self.0.is_some_and(|(t, p, k)| k == kind && now - t <= DOUBLE_CLICK_S && p.distance(at) <= DOUBLE_CLICK_PX);
        self.0 = if double { None } else { Some((now, at, kind)) };
        double
    }
}

#[derive(Resource, Default)]
pub struct OrderMode {
    pub attack_move: bool,
    pub set_rally: bool,
    /// World point of the last order (for a short marker).
    pub last_order: Option<(Vec2, f32, bool)>,
}

#[derive(Component)]
pub struct DragRect;

pub struct SelectionPlugin;

impl Plugin for SelectionPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Selection>()
            .init_resource::<DragState>()
            .init_resource::<OrderMode>()
            .add_systems(OnEnter(AppState::InGame), setup_drag_rect)
            .add_systems(Update, (selection_input, hotkeys).run_if(in_state(AppState::InGame)).run_if(|p: Res<crate::menu::PauseState>, c: Res<crate::console::ConsoleState>| !p.open && !c.open && !c.menu))
            .add_systems(Update, (draw_selection, update_drag_rect).run_if(in_state(AppState::InGame)));
    }
}

fn setup_drag_rect(mut commands: Commands) {
    commands.spawn((
        DragRect,
        DespawnOnExit(AppState::InGame),
        Node { position_type: PositionType::Absolute, left: px(0), top: px(0), width: px(0), height: px(0), border: UiRect::all(px(1)), ..default() },
        BorderColor::all(Color::srgba(0.9, 1.0, 0.6, 0.9)),
        BackgroundColor(Color::srgba(0.7, 1.0, 0.4, 0.12)),
        Visibility::Hidden,
    ));
}

#[allow(clippy::too_many_arguments)]
fn selection_input(
    buttons: Res<ButtonInput<MouseButton>>,
    keys: Res<ButtonInput<KeyCode>>,
    controls: Res<Controls>,
    windows: Query<&Window, With<PrimaryWindow>>,
    cameras: Query<(&Camera, &GlobalTransform), With<MainCamera>>,
    mut sim: ResMut<GameSim>,
    mut selection: ResMut<Selection>,
    mut drag: ResMut<DragState>,
    mut mode: ResMut<OrderMode>,
    mut pending: ResMut<PendingOrders>,
    time: Res<Time>,
    real: Res<Time<Real>>,
    sidebar: Res<crate::orig_ui::SidebarWidth>,
) {
    let Ok(window) = windows.single() else { return };
    let Ok((camera, cam_tf)) = cameras.single() else { return };
    let Some(cursor) = window.cursor_position() else { return };
    let team = sim.human_team();
    let add = controls.pressed(&keys, "add_to_selection");
    // the sidebar covers the right edge: clicks there are interface clicks, never map orders
    let over_sidebar = cursor.x >= window.width() - sidebar.0;
    if over_sidebar && drag.start.is_none() {
        return;
    }

    if buttons.just_pressed(MouseButton::Left) {
        drag.start = Some(cursor);
        drag.dragging = false;
    }
    if buttons.pressed(MouseButton::Left)
        && let Some(s) = drag.start
    {
        drag.current = cursor;
        if (cursor - s).length() > controls.drag_threshold {
            drag.dragging = true;
        }
    }
    if buttons.just_released(MouseButton::Left)
        && let Some(start) = drag.start.take()
    {
        if mode.attack_move {
            // attack-move click
            mode.attack_move = false;
            if let Some(p) = cursor_ground_point(camera, cam_tf, cursor)
                && !selection.units.is_empty()
            {
                pending.0.push((selection.units.clone(), Order::AttackMove(p)));
                mode.last_order = Some((p, time.elapsed_secs(), true));
            }
            drag.dragging = false;
            return;
        }
        if mode.set_rally {
            mode.set_rally = false;
            if let (Some(p), Some(c)) = (cursor_ground_point(camera, cam_tf, cursor), selection.colony) {
                sim.world.set_rally(c, p);
            }
            drag.dragging = false;
            return;
        }
        let mut picked: Vec<UnitId> = Vec::new();
        let mut picked_colony = None;
        if drag.dragging {
            let min = start.min(cursor);
            let max = start.max(cursor);
            for u in sim.world.living_units() {
                if u.team != team || !sim.world.unit_def(u).controllable {
                    continue;
                }
                let wp = Vec3::new(u.pos.x, 0.3, u.pos.y);
                if let Ok(sp) = camera.world_to_viewport(cam_tf, wp)
                    && sp.x >= min.x
                    && sp.x <= max.x
                    && sp.y >= min.y
                    && sp.y <= max.y
                {
                    picked.push(u.id);
                }
            }
        } else if let Some(p) = cursor_ground_point(camera, cam_tf, cursor) {
            // pick the nearest unit under the cursor (own units preferred), else a colony
            let mut best: Option<(f32, UnitId)> = None;
            for u in sim.world.living_units() {
                let d = u.pos.distance(p) - sim.world.unit_def(u).radius;
                if d <= 0.45 {
                    let score = d - if u.team == team { 1.0 } else { 0.0 };
                    if best.is_none_or(|(bs, _)| score < bs) {
                        best = Some((score, u.id));
                    }
                }
            }
            if let Some((_, id)) = best {
                if let Some(kind) = sim.world.unit(id).filter(|u| u.team == team).map(|u| u.kind) {
                    if drag.last_click.click(real.elapsed_secs(), cursor, kind) {
                        // double click: every bug of this kind in the 3-D view (left of the sidebar)
                        let view = Vec2::new(window.width() - sidebar.0, window.height());
                        for u in sim.world.living_units() {
                            if u.team != team || u.kind != kind || !sim.world.unit_def(u).controllable {
                                continue;
                            }
                            if let Ok(sp) = camera.world_to_viewport(cam_tf, Vec3::new(u.pos.x, 0.3, u.pos.y))
                                && sp.x >= 0.0
                                && sp.y >= 0.0
                                && sp.x <= view.x
                                && sp.y <= view.y
                            {
                                picked.push(u.id);
                            }
                        }
                    } else {
                        picked.push(id);
                    }
                }
            } else {
                picked_colony = sim.world.pick_colony(p);
            }
        }
        if !add {
            selection.units.clear();
            selection.colony = None;
        }
        for id in picked {
            if !selection.units.contains(&id) {
                selection.units.push(id);
            }
        }
        if let Some(c) = picked_colony {
            selection.colony = Some(c);
            selection.units.clear();
        }
        drag.dragging = false;
    }

    // orders with the right mouse button
    if buttons.just_pressed(MouseButton::Right) {
        if let Some(p) = cursor_ground_point(camera, cam_tf, cursor) {
            if mode.set_rally
                && let Some(c) = selection.colony
            {
                sim.world.set_rally(c, p);
                mode.set_rally = false;
                return;
            }
            if !selection.units.is_empty() {
                // enemy unit or colony under the cursor?
                let target = sim
                    .world
                    .pick_unit(p, 0.5)
                    .filter(|id| sim.world.unit(*id).is_some_and(|u| u.team != team))
                    .map(Target::Unit)
                    .or_else(|| sim.world.pick_colony(p).filter(|c| sim.world.colonies[*c as usize].team != team && sim.world.colonies[*c as usize].active()).map(Target::Colony));
                let order = match target {
                    Some(t) => Order::Attack(t),
                    None => {
                        if mode.attack_move {
                            Order::AttackMove(p)
                        } else {
                            Order::Move(p)
                        }
                    }
                };
                mode.attack_move = false;
                pending.0.push((selection.units.clone(), order));
                mode.last_order = Some((p, time.elapsed_secs(), matches!(order, Order::Attack(_) | Order::AttackMove(_))));
            } else if let Some(c) = selection.colony
                && sim.world.colonies[c as usize].team == team
            {
                sim.world.set_rally(c, p);
            }
        }
    }

    // drop dead units from the selection
    let world = &sim.world;
    selection.units.retain(|id| world.unit(*id).is_some_and(|u| u.alive()));
}

#[allow(clippy::too_many_arguments)]
fn hotkeys(
    keys: Res<ButtonInput<KeyCode>>,
    controls: Res<Controls>,
    mut sim: ResMut<GameSim>,
    mut selection: ResMut<Selection>,
    mut mode: ResMut<OrderMode>,
    mut pending: ResMut<PendingOrders>,
    mut lib: Option<ResMut<crate::audio::AudioLibrary>>,
    mut commands: Commands,
) {
    let team = sim.human_team();
    if controls.just_pressed(&keys, "select_all") {
        selection.units = sim.world.living_units().filter(|u| u.team == team && sim.world.unit_def(u).controllable).map(|u| u.id).collect();
        selection.colony = None;
    }
    if controls.just_pressed(&keys, "attack_move") && !selection.units.is_empty() {
        mode.attack_move = !mode.attack_move;
    }
    if controls.just_pressed(&keys, "stop") && !selection.units.is_empty() {
        pending.0.push((selection.units.clone(), Order::Stop));
    }
    if let Some(c) = selection.colony
        && sim.world.colonies.get(c as usize).is_some_and(|c| c.team == team && c.active())
    {
        let roster: Vec<u16> = sim.world.colony_def(&sim.world.colonies[c as usize]).produces.iter().filter_map(|p| sim.world.defs.unit(p)).collect();
        for (i, action) in ["breed_1", "breed_2", "breed_3"].iter().enumerate() {
            if controls.just_pressed(&keys, action)
                && let Some(kind) = roster.get(i)
            {
                sim.world.set_production(c, Some(*kind));
                if let Some(lib) = lib.as_mut() {
                    lib.play_ui(&mut commands, "production_change", 0.8);
                }
            }
        }
        if controls.just_pressed(&keys, "breed_stop") {
            sim.world.set_production(c, None);
            if let Some(lib) = lib.as_mut() {
                lib.play_ui(&mut commands, "production_stop", 0.8);
            }
        }
        if controls.just_pressed(&keys, "set_rally") {
            mode.set_rally = true;
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn draw_selection(sim: Res<GameSim>, selection: Res<Selection>, mode: Res<OrderMode>, time: Res<Time>, ground: Option<Res<crate::ground::GroundHeight>>, orig: Option<Res<crate::orig_ui::OrigUi>>, mut gizmos: Gizmos) {
    let gy = |p: Vec2| crate::views::ground_at(&ground, p);
    let flat = Quat::from_rotation_x(-std::f32::consts::FRAC_PI_2);
    let team = sim.human_team();
    let color = {
        let [r, g, b] = sa_sim::team_rgb(&sim.world.teams[team as usize].def.color);
        Color::srgb((r + 0.4).min(1.0), (g + 0.4).min(1.0), (b + 0.4).min(1.0))
    };
    for id in &selection.units {
        if let Some(u) = sim.world.unit(*id) {
            let r = sim.world.unit_def(u).radius + 0.15;
            let p = u.prev_pos.lerp(u.pos, sim.alpha);
            gizmos.circle(Isometry3d::new(Vec3::new(p.x, gy(p) + 0.04, p.y), flat), r, color);
            // health: green->red bar above the unit (with the original game, its own bars: orig_select.rs)
            if orig.is_some() {
                continue;
            }
            let def = sim.world.unit_def(u);
            let frac = (u.hp / def.hp).clamp(0.0, 1.0);
            let base = Vec3::new(p.x - r, gy(p) + def.altitude + 1.1, p.y);
            gizmos.line(base, base + Vec3::X * 2.0 * r, Color::srgb(0.2, 0.2, 0.2));
            gizmos.line(base, base + Vec3::X * 2.0 * r * frac, Color::srgb(1.0 - frac, frac, 0.1));
        }
    }
    if let Some(c) = selection.colony
        && let Some(col) = sim.world.colonies.get(c as usize)
    {
        let half = sim.world.colony_def(col).half_extent + 0.3;
        gizmos.rect(Isometry3d::new(Vec3::new(col.pos.x, gy(col.pos) + 0.05, col.pos.y), flat), Vec2::splat(half * 2.0), color);
        let r = Vec3::new(col.rally.x, gy(col.rally) + 0.1, col.rally.y);
        gizmos.circle(Isometry3d::new(r, flat), 0.4, Color::srgb(0.9, 0.9, 0.3));
        gizmos.line(Vec3::new(col.pos.x, gy(col.pos) + 0.1, col.pos.y), r, Color::srgba(0.9, 0.9, 0.3, 0.5));
    }
    if let Some((p, t, attack)) = mode.last_order {
        let age = time.elapsed_secs() - t;
        if age < 1.0 {
            let r = 0.3 + age * 0.8;
            let c = if attack { Color::srgba(1.0, 0.3, 0.2, 1.0 - age) } else { Color::srgba(0.4, 1.0, 0.4, 1.0 - age) };
            gizmos.circle(Isometry3d::new(Vec3::new(p.x, gy(p) + 0.06, p.y), flat), r, c);
        }
    }
    if mode.attack_move {
        // small pulsing ring on every selected unit to show attack-move mode
        let pulse = 0.5 + 0.5 * (time.elapsed_secs() * 8.0).sin();
        for id in &selection.units {
            if let Some(u) = sim.world.unit(*id) {
                gizmos.circle(Isometry3d::new(Vec3::new(u.pos.x, gy(u.pos) + 0.08, u.pos.y), flat), 0.6 + pulse * 0.2, Color::srgb(1.0, 0.4, 0.2));
            }
        }
    }
}

fn update_drag_rect(drag: Res<DragState>, mut q: Query<(&mut Node, &mut Visibility), With<DragRect>>) {
    for (mut node, mut vis) in q.iter_mut() {
        if drag.dragging
            && let Some(s) = drag.start
        {
            let min = s.min(drag.current);
            let max = s.max(drag.current);
            node.left = px(min.x);
            node.top = px(min.y);
            node.width = px(max.x - min.x);
            node.height = px(max.y - min.y);
            *vis = Visibility::Visible;
        } else {
            *vis = Visibility::Hidden;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn double_click_needs_the_same_kind_quickly_and_in_place() {
        let mut c = LastClick::default();
        assert!(!c.click(1.0, Vec2::new(100.0, 100.0), 3));
        assert!(c.click(1.3, Vec2::new(103.0, 101.0), 3));
        assert!(!c.click(1.5, Vec2::new(103.0, 101.0), 3), "a third click starts a new pair");
        assert!(!c.click(2.5, Vec2::new(103.0, 101.0), 3), "too slow");
        assert!(c.click(2.8, Vec2::new(101.0, 100.0), 3));
        let mut c = LastClick::default();
        assert!(!c.click(1.0, Vec2::ZERO, 3));
        assert!(!c.click(1.2, Vec2::ZERO, 4), "another kind of bug");
        let mut c = LastClick::default();
        assert!(!c.click(1.0, Vec2::ZERO, 3));
        assert!(!c.click(1.2, Vec2::new(30.0, 0.0), 3), "too far apart");
    }
}
