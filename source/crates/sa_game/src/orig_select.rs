//! The original's health bars: a small vertical bar in a white bracket beside every selected unit
//! (SELECT1..27) and a tall one beside the selected colony (SELECTC1..73), going from green through
//! yellow to red as health drops, grey for the part that is lost. Drawn on screen next to the 3-D
//! model and sized with the zoom (the original drew them at 24 pixels per cell).

use std::collections::HashMap;

use bevy::picking::Pickable;
use bevy::prelude::*;
use bevy::state::state_scoped::DespawnOnExit;
use bevy::window::PrimaryWindow;

use crate::AppState;
use crate::orig_ui::{OrigUi, SidebarWidth};
use crate::selection::Selection;
use crate::sim_plugin::GameSim;

pub struct OrigSelectPlugin;

impl Plugin for OrigSelectPlugin {
    fn build(&self, app: &mut App) {
        if !app.world().contains_resource::<OrigUi>() {
            return;
        }
        app.add_systems(PostUpdate, selection_bars.after(bevy::transform::TransformSystems::Propagate).run_if(in_state(AppState::InGame)));
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Hash)]
enum Key {
    Unit(sa_sim::UnitId),
    Colony(u32),
}

#[derive(Component)]
struct SelectionBar;

#[allow(clippy::too_many_arguments)]
fn selection_bars(
    mut commands: Commands,
    sim: Res<GameSim>,
    selection: Res<Selection>,
    mut ui: ResMut<OrigUi>,
    mut images: ResMut<Assets<Image>>,
    cameras: Query<(&Camera, &GlobalTransform), With<Camera3d>>,
    windows: Query<&Window, With<PrimaryWindow>>,
    sidebar: Option<Res<SidebarWidth>>,
    ground: Option<Res<crate::ground::GroundHeight>>,
    mut bars: Query<(&mut Node, &mut ImageNode, &mut Visibility), With<SelectionBar>>,
    mut index: Local<HashMap<Key, Entity>>,
) {
    let Ok((camera, cam_tf)) = cameras.single() else { return };
    let view_right = windows.single().map(|w| w.width()).unwrap_or(1280.0) - sidebar.map(|s| s.0).unwrap_or(0.0);
    // what is selected: (key, ground position, height of the body's middle, half width, health fraction)
    let mut want: Vec<(Key, Vec2, f32, f32, f32)> = Vec::new();
    for id in &selection.units {
        if let Some(u) = sim.world.unit(*id).filter(|u| u.alive()) {
            let def = sim.world.unit_def(u);
            let p = u.prev_pos.lerp(u.pos, sim.alpha);
            want.push((Key::Unit(*id), p, def.altitude + 0.3, def.radius, (u.hp / def.hp).clamp(0.0, 1.0)));
        }
    }
    if let Some(c) = selection.colony
        && let Some(col) = sim.world.colonies.get(c as usize)
    {
        let def = sim.world.colony_def(col);
        want.push((Key::Colony(c), col.pos, 1.0, def.half_extent, (col.hp / def.hp).clamp(0.0, 1.0)));
    }
    // drop bars of what is no longer selected
    index.retain(|k, e| {
        let keep = want.iter().any(|w| w.0 == *k);
        if !keep {
            commands.entity(*e).despawn();
        }
        keep
    });
    for (key, p, height, half, frac) in want {
        let base = crate::views::ground_at(&ground, p);
        let world = Vec3::new(p.x, base + height, p.y);
        let (Ok(at), Ok(one)) = (camera.world_to_viewport(cam_tf, world), camera.world_to_viewport(cam_tf, world + Vec3::X)) else { continue };
        let per_cell = at.distance(one).max(4.0);
        let scale = per_cell / 24.0;
        let (name, w, h) = match key {
            Key::Unit(_) => (format!("SELECT{}", 1 + ((1.0 - frac) * 26.0).round() as u32), 10.0, 32.0),
            Key::Colony(_) => (format!("SELECTC{}", 1 + ((1.0 - frac) * 72.0).round() as u32), 16.0, 80.0),
        };
        let Some(image) = ui.pic_keyed(&mut images, &name) else { continue };
        let (w, h) = (w * scale, h * scale);
        let left = at.x - half * per_cell - w - 2.0 * scale;
        let top = at.y - h * 0.5;
        let visible = left + w < view_right && at.x > -50.0;
        let entity = *index.entry(key).or_insert_with(|| {
            commands.spawn((SelectionBar, DespawnOnExit(AppState::InGame), ImageNode::new(image.clone()), Node { position_type: PositionType::Absolute, ..default() }, GlobalZIndex(1), Pickable::IGNORE)).id()
        });
        if let Ok((mut node, mut img, mut vis)) = bars.get_mut(entity) {
            node.left = px(left);
            node.top = px(top);
            node.width = px(w);
            node.height = px(h);
            if img.image != image {
                img.image = image;
            }
            let v = if visible { Visibility::Inherited } else { Visibility::Hidden };
            if *vis != v {
                *vis = v;
            }
        }
    }
}
