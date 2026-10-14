//! Shared interface pieces: the chrome rendered in Blender (blender/scripts/build_ui_chrome.py),
//! the dialog buttons with their hover/pressed art, the font, the red cursors and the click sound.

use std::collections::HashMap;

use bevy::audio::{AudioPlayer, PlaybackSettings, Volume};
use bevy::picking::hover::Hovered;
use bevy::prelude::*;
use bevy::text::{FontSize, FontSource};
use bevy::ui::{InteractionDisabled, Pressed, VisualBox};
use bevy::ui_widgets::{Activate, ActivateOnPress, Button};
use bevy::window::{CursorIcon, CustomCursor, CustomCursorImage, PrimaryWindow};

use crate::AppState;
use crate::asset_root;
use crate::audio::AudioLibrary;
use crate::camera::{MainCamera, cursor_ground_point};
use crate::selection::{DragState, OrderMode, Selection};
use crate::sim_plugin::GameSim;

/// Width of the sidebar (the original's 226-pixel panel); clicks under it never reach the map.
pub const SIDEBAR_WIDTH: f32 = 226.0;
pub const TEXT: Color = Color::srgb(0.95, 0.92, 0.80);
pub const DIM: Color = Color::srgb(0.72, 0.68, 0.56);
pub const GOLD: Color = Color::srgb(0.96, 0.82, 0.36);
pub const BACKDROP: Color = Color::srgb(0.06, 0.055, 0.045);

#[derive(Resource)]
pub struct UiAssets {
    pub font: Handle<Font>,
    pub sidebar: Handle<Image>,
    pub button: Handle<Image>,
    pub button_pressed: Handle<Image>,
    /// normal, hover, pressed, disabled
    pub dbutton: [Handle<Image>; 4],
    pub bar: Handle<Image>,
    pub bar_dim: Handle<Image>,
    pub led: Handle<Image>,
    pub led_red: Handle<Image>,
    pub led_off: Handle<Image>,
    pub dialog: Handle<Image>,
    pub blackbar: Handle<Image>,
    emblems: HashMap<String, Handle<Image>>,
    /// arrow, attack, select
    cursors: [Handle<Image>; 3],
    icons: HashMap<String, Option<Handle<Image>>>,
    portraits: HashMap<String, Handle<Image>>,
}

impl UiAssets {
    fn load(server: &AssetServer) -> Self {
        let img = |name: &str| server.load::<Image>(format!("ui/{name}.png"));
        let mut emblems = HashMap::new();
        for fam in ["ant", "beetle", "spider", "scorpion", "wasp"] {
            emblems.insert(fam.to_string(), img(&format!("emblem_{fam}")));
        }
        Self {
            font: server.load("fonts/FreeSansBold.ttf"),
            sidebar: img("sidebar"),
            button: img("button"),
            button_pressed: img("button_pressed"),
            dbutton: [img("dbutton_normal"), img("dbutton_hover"), img("dbutton_pressed"), img("dbutton_disabled")],
            bar: img("bar"),
            bar_dim: img("bar_dim"),
            led: img("led"),
            led_red: img("led_red"),
            led_off: img("led_off"),
            dialog: img("dialog"),
            blackbar: img("blackbar"),
            emblems,
            cursors: [img("cursor_arrow"), img("cursor_attack"), img("cursor_select")],
            icons: HashMap::new(),
            portraits: HashMap::new(),
        }
    }

    pub fn text(&self, size: f32) -> TextFont {
        TextFont { font: FontSource::Handle(self.font.clone()), font_size: FontSize::Px(size), ..default() }
    }

    /// Faction insignia (`emblem_<family>.png`), the ants' when the family has none.
    pub fn emblem(&self, family: &str) -> Handle<Image> {
        self.emblems.get(family).or_else(|| self.emblems.get("ant")).cloned().unwrap_or_default()
    }

    /// Transparent top-down icon of a unit model (`ui/icon_<model>.png`) when one exists.
    pub fn icon(&mut self, server: &AssetServer, model: &str) -> Option<Handle<Image>> {
        self.icons
            .entry(model.to_string())
            .or_insert_with(|| {
                let rel = format!("ui/icon_{model}.png");
                std::path::Path::new(&asset_root()).join(&rel).exists().then(|| server.load(rel))
            })
            .clone()
    }

    /// Portrait crop of any model (`ui/portraits/<model>.png`).
    pub fn portrait(&mut self, server: &AssetServer, model: &str) -> Handle<Image> {
        self.portraits.entry(model.to_string()).or_insert_with(|| server.load(format!("ui/portraits/{model}.png"))).clone()
    }

    /// Picture for the selection screen: the icon when there is one, else the portrait.
    pub fn picture(&mut self, server: &AssetServer, model: &str) -> Handle<Image> {
        self.icon(server, model).unwrap_or_else(|| self.portrait(server, model))
    }
}

pub fn sliced(border: f32) -> NodeImageMode {
    NodeImageMode::Sliced(TextureSlicer { border: BorderRect::all(border), center_scale_mode: SliceScaleMode::Stretch, sides_scale_mode: SliceScaleMode::Stretch, max_corner_scale: 1.0 })
}

/// Stone dialog frame (9-slice) used by every menu panel.
pub fn dialog_panel(ui: &UiAssets) -> (ImageNode, Node) {
    (
        ImageNode { image: ui.dialog.clone(), image_mode: sliced(30.0), visual_box: VisualBox::BorderBox, ..default() },
        Node { flex_direction: FlexDirection::Column, align_items: AlignItems::Center, padding: UiRect::axes(px(34), px(30)), ..default() },
    )
}

/// Black rounded bar with a steel rim (messages, console).
pub fn black_bar(ui: &UiAssets) -> ImageNode {
    ImageNode { image: ui.blackbar.clone(), image_mode: sliced(20.0), visual_box: VisualBox::BorderBox, ..default() }
}

/// Text with a dark drop shadow (legible on stone and metal).
pub fn shadow() -> TextShadow {
    TextShadow { offset: Vec2::new(1.0, 1.0), color: Color::srgba(0.0, 0.0, 0.0, 0.85) }
}

#[derive(Component)]
pub struct DialogButton;

/// Bronze dialog button (the art swaps on hover and press).
pub fn dialog_button<B: Bundle>(parent: &mut ChildSpawnerCommands, ui: &UiAssets, label: &str, width: f32, extra: B) -> Entity {
    parent
        .spawn((
            Button,
            ActivateOnPress,
            Hovered::default(),
            DialogButton,
            extra,
            ImageNode { image: ui.dbutton[0].clone(), image_mode: sliced(12.0), visual_box: VisualBox::BorderBox, ..default() },
            Node { width: px(width), height: px(30), margin: UiRect::all(px(3)), justify_content: JustifyContent::Center, align_items: AlignItems::Center, ..default() },
            children![(Text::new(label), ui.text(15.0), TextColor(TEXT), shadow())],
        ))
        .id()
}

/// Greyed-out, inactive entry (a locked level).
pub fn locked_button(parent: &mut ChildSpawnerCommands, ui: &UiAssets, label: &str, width: f32) {
    parent.spawn((
        ImageNode { image: ui.dbutton[3].clone(), image_mode: sliced(12.0), visual_box: VisualBox::BorderBox, ..default() },
        Node { width: px(width), height: px(30), margin: UiRect::all(px(3)), justify_content: JustifyContent::Center, align_items: AlignItems::Center, ..default() },
        children![(Text::new(label), ui.text(15.0), TextColor(Color::srgba(0.6, 0.58, 0.5, 0.9)), shadow())],
    ));
}

#[derive(Clone, Copy, PartialEq, Eq, Default, Debug)]
pub enum CursorKind {
    #[default]
    Arrow,
    Attack,
    Select,
}

pub struct UiPlugin;

impl Plugin for UiPlugin {
    fn build(&self, app: &mut App) {
        // loaded while the app is built: the first state transition (menu or level) needs it
        let server = app.world().resource::<AssetServer>().clone();
        app.insert_resource(UiAssets::load(&server)).add_systems(Update, (dialog_button_style, update_cursor)).add_observer(click_sound);
    }
}

fn dialog_button_style(ui: Res<UiAssets>, mut q: Query<(&Hovered, Has<Pressed>, Has<InteractionDisabled>, &mut ImageNode), With<DialogButton>>) {
    for (h, pressed, disabled, mut img) in &mut q {
        let want = if disabled {
            &ui.dbutton[3]
        } else if pressed {
            &ui.dbutton[2]
        } else if h.get() {
            &ui.dbutton[1]
        } else {
            &ui.dbutton[0]
        };
        if img.image != *want {
            img.image = want.clone();
        }
    }
}

/// Red cursors like the original's: arrow, crosshair over an enemy (or in attack-move mode) and
/// the selection bracket while dragging a box.
#[allow(clippy::too_many_arguments)]
fn update_cursor(
    mut commands: Commands,
    ui: Res<UiAssets>,
    state: Res<State<AppState>>,
    sim: Option<Res<GameSim>>,
    selection: Option<Res<Selection>>,
    drag: Option<Res<DragState>>,
    mode: Option<Res<OrderMode>>,
    pause: Option<Res<crate::menu::PauseState>>,
    console: Option<Res<crate::console::ConsoleState>>,
    windows: Query<(Entity, &Window), With<PrimaryWindow>>,
    cameras: Query<(&Camera, &GlobalTransform), With<MainCamera>>,
    mut last: Local<Option<CursorKind>>,
) {
    let Ok((entity, window)) = windows.single() else { return };
    let mut kind = CursorKind::Arrow;
    let menus_open = pause.is_some_and(|p| p.open) || console.is_some_and(|c| c.open || c.menu);
    if *state.get() == AppState::InGame
        && !menus_open
        && let (Some(sim), Some(selection)) = (sim.as_ref(), selection.as_ref())
    {
        if drag.as_ref().is_some_and(|d| d.dragging) {
            kind = CursorKind::Select;
        } else if let Some(cursor) = window.cursor_position()
            && cursor.x < window.width() - SIDEBAR_WIDTH
            && !selection.units.is_empty()
        {
            if mode.as_ref().is_some_and(|m| m.attack_move) {
                kind = CursorKind::Attack;
            } else if let Ok((camera, tf)) = cameras.single()
                && let Some(p) = cursor_ground_point(camera, tf, cursor)
            {
                let team = sim.human_team();
                let w = &sim.world;
                let enemy_unit = w.pick_unit(p, 0.5).and_then(|id| w.unit(id)).is_some_and(|u| w.is_enemy(team, u.team));
                let enemy_colony = w.pick_colony(p).is_some_and(|c| {
                    let col = &w.colonies[c as usize];
                    col.active() && w.is_enemy(team, col.team)
                });
                if enemy_unit || enemy_colony {
                    kind = CursorKind::Attack;
                }
            }
        }
    }
    if *last != Some(kind) {
        *last = Some(kind);
        let (handle, hotspot) = match kind {
            CursorKind::Arrow => (ui.cursors[0].clone(), (2, 2)),
            CursorKind::Attack => (ui.cursors[1].clone(), (15, 15)),
            CursorKind::Select => (ui.cursors[2].clone(), (15, 15)),
        };
        commands.entity(entity).insert(CursorIcon::Custom(CustomCursor::Image(CustomCursorImage { handle, texture_atlas: None, flip_x: false, flip_y: false, rect: None, hotspot })));
    }
}

/// Every button press plays the interface click when the sound file exists.
fn click_sound(_ev: On<Activate>, lib: Option<Res<AudioLibrary>>, mut commands: Commands) {
    let Some(lib) = lib else { return };
    if !lib.enabled {
        return;
    }
    if let Some(h) = lib.sounds.get("ui_click") {
        commands.spawn((AudioPlayer::new(h.clone()), PlaybackSettings::DESPAWN.with_volume(Volume::Linear(lib.master_volume * 0.7))));
    }
}
