//! Original-style interface: the stone-and-steel sidebar (game timer, faction insignia, radar, the
//! three breeding buttons with their red bars and the LED), the selection screen under it and the
//! black message bar at the bottom. Debug statistics (F3) and the controls help (F1) stay hidden
//! unless asked for. Layout positions are those of the original 226x448 panel.

use bevy::asset::RenderAssetUsages;
use bevy::diagnostic::{DiagnosticsStore, FrameTimeDiagnosticsPlugin};
use bevy::image::ImageSampler;
use bevy::picking::hover::Hovered;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};
use bevy::state::state_scoped::DespawnOnExit;
use bevy::text::Justify;
use bevy::ui::RelativeCursorPosition;
use bevy::ui_widgets::{Activate, ActivateOnPress, Button};
use sa_sim::{ColonyState, SimEvent, TerrainKind};

use crate::AppState;
use crate::camera::RtsCamera;
use crate::controls::Controls;
use crate::menu::MenuAction;
use crate::selection::{OrderMode, Selection};
use crate::sim_plugin::GameSim;
use crate::terrain::NavDebug;
pub use crate::ui::SIDEBAR_WIDTH;
use crate::ui::{DIM, TEXT, UiAssets, black_bar, shadow};

// pixel layout of the panel (from its top-left corner)
const INSIGNIA: (f32, f32, f32) = (72.0, 8.0, 82.0);
const TIMER: (f32, f32, f32) = (13.0, 20.0, 53.0);
const RADAR: (f32, f32, f32) = (13.0, 108.0, 202.0);
const BUTTON_X: [f32; 3] = [26.0, 87.0, 147.0];
const BUTTON_Y: f32 = 330.0;
const BAR_X: [f32; 3] = [25.0, 86.0, 146.0];
const BAR_Y: f32 = 393.0;
const LED: (f32, f32) = (103.0, 418.0);
const SELECT: (f32, f32, f32, f32) = (17.0, 468.0, 194.0, 96.0);
const MESSAGE_BAR: (f32, f32) = (416.0, 46.0);

#[derive(Component)]
pub struct Sidebar;
#[derive(Component)]
struct MinimapNode;
#[derive(Component)]
struct PortraitNode;
#[derive(Component)]
struct SelNameText;
#[derive(Component)]
struct SelInfoText;
#[derive(Component)]
struct HpBar;
#[derive(Component)]
struct HpFill;
#[derive(Component)]
pub struct BreedButton(pub usize);
#[derive(Component)]
struct BreedIcon(usize);
#[derive(Component)]
struct BreedBar(usize);
#[derive(Component)]
struct BreedBarImage(usize);
#[derive(Component)]
struct LedNode;
#[derive(Component)]
struct TimerText;
#[derive(Component)]
struct MessageText;
#[derive(Component)]
pub struct DebugText;
#[derive(Component)]
pub struct HelpText;

/// Timed messages shown in the black bar under the map (events, hints, console output).
#[derive(Resource, Default)]
pub struct Messages {
    lines: Vec<(String, f32)>,
}

impl Messages {
    pub fn push(&mut self, text: impl Into<String>) {
        let text = text.into();
        info!("{text}");
        self.lines.push((text, 5.0));
        if self.lines.len() > 4 {
            self.lines.remove(0);
        }
    }
}

#[derive(Resource, Default)]
pub struct HudToggles {
    pub help: bool,
}

#[derive(Resource)]
struct Minimap {
    handle: Handle<Image>,
    w: u32,
    h: u32,
    timer: f32,
    base: Vec<u8>,
}

pub const HELP: &str = "Mouse: left click / drag selects, right click moves or attacks, wheel zooms, middle drag pans\n\
Double-click a bug: every bug of that kind on the screen   T attack-move   X stop   C select all   Shift adds\n\
Colony: click it, then the three buttons (or 1 / 2 / 3) choose what it breeds, 0 stops, R + click sets the rally point\n\
WASD or screen edges pan, Q / E rotate, Home centres, Space pauses, [ ] game speed\n\
The insignia at the top of the panel opens the menu (also Esc)\n\
Enter opens the console (type help), F1 this help, F3 debug view, F5 / F9 quick save / load, F12 screenshot";

pub struct HudPlugin;

impl Plugin for HudPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins(FrameTimeDiagnosticsPlugin::default())
            .init_resource::<Messages>()
            .init_resource::<HudToggles>()
            .add_systems(OnEnter(AppState::InGame), setup_hud)
            .add_systems(Update, (hud_keys, console_select, update_selection_panel, update_breed_panel, update_timer, update_minimap, update_messages, update_debug, minimap_click).run_if(in_state(AppState::InGame)))
            .add_observer(on_breed);
    }
}

fn terrain_pixel(kind: TerrainKind, tileset: &str) -> [u8; 4] {
    match (tileset, kind) {
        ("desert", TerrainKind::Clear) => [196, 160, 100, 255],
        ("desert", TerrainKind::Rock) => [140, 128, 116, 255],
        ("desert", TerrainKind::Vegetation) => [110, 86, 48, 255],
        ("desert", TerrainKind::Water) => [74, 64, 58, 255],
        ("swamp", TerrainKind::Clear) => [98, 106, 68, 255],
        ("swamp", TerrainKind::Rock) => [74, 88, 52, 255],
        ("swamp", TerrainKind::Vegetation) => [52, 58, 96, 255],
        ("swamp", TerrainKind::Water) => [44, 84, 64, 255],
        ("candy", TerrainKind::Clear) => [190, 170, 160, 255],
        ("candy", TerrainKind::Rock) => [172, 138, 120, 255],
        ("candy", TerrainKind::Vegetation) => [146, 44, 48, 255],
        ("candy", TerrainKind::Water) => [116, 102, 130, 255],
        (_, TerrainKind::Clear) => [112, 150, 70, 255],
        (_, TerrainKind::Rock) => [136, 128, 112, 255],
        (_, TerrainKind::Vegetation) => [60, 108, 44, 255],
        (_, TerrainKind::Water) => [56, 104, 172, 255],
    }
}

/// Family of the human player's side (its first colony, else its first unit): picks the insignia.
fn human_family(sim: &GameSim) -> String {
    let human = sim.human_team();
    let w = &sim.world;
    let fam = w
        .colonies
        .iter()
        .find(|c| c.team == human && c.active())
        .map(|c| w.colony_def(c).family)
        .or_else(|| w.living_units().find(|u| u.team == human).map(|u| w.unit_def(u).family))
        .unwrap_or(sa_sim::Family::Ant);
    format!("{fam:?}").to_ascii_lowercase()
}

fn setup_hud(mut commands: Commands, sim: Res<GameSim>, mut images: ResMut<Assets<Image>>, ui: Res<UiAssets>, orig: Option<Res<crate::orig_ui::OrigUi>>) {
    // with the original game's interface its own sidebar replaces this one (orig_ui.rs)
    if orig.is_none() {
        spawn_sidebar(&mut commands, &sim, &mut images, &ui);
    }
    spawn_overlays(&mut commands, &ui);
}

fn spawn_sidebar(commands: &mut Commands, sim: &GameSim, images: &mut Assets<Image>, ui: &UiAssets) {
    let grid = &sim.world.grid;
    let (w, h) = (grid.w as u32, grid.h as u32);
    let mut base = Vec::with_capacity((w * h * 4) as usize);
    for y in 0..h as i32 {
        for x in 0..w as i32 {
            base.extend_from_slice(&terrain_pixel(grid.terrain_kind(IVec2::new(x, y)), &sim.world.map.tileset));
        }
    }
    let mut image = Image::new(Extent3d { width: w, height: h, depth_or_array_layers: 1 }, TextureDimension::D2, base.clone(), TextureFormat::Rgba8UnormSrgb, RenderAssetUsages::MAIN_WORLD | RenderAssetUsages::RENDER_WORLD);
    image.sampler = ImageSampler::nearest();
    let handle = images.add(image);
    commands.insert_resource(Minimap { handle: handle.clone(), w, h, timer: 0.0, base });
    let family = human_family(sim);

    commands
        .spawn((
            Sidebar,
            DespawnOnExit(AppState::InGame),
            Node { position_type: PositionType::Absolute, top: px(0), right: px(0), width: px(SIDEBAR_WIDTH), height: percent(100), overflow: Overflow::clip(), ..default() },
            BackgroundColor(Color::srgb(0.09, 0.08, 0.06)),
            GlobalZIndex(5),
        ))
        .with_children(|p| {
            // the rendered panel (226x1080: the original 448-pixel chrome on top, the slab continues below)
            p.spawn((ImageNode::new(ui.sidebar.clone()), Node { position_type: PositionType::Absolute, left: px(0), top: px(0), width: px(226), height: px(1080), ..default() }));
            // game timer in the pill
            p.spawn((
                TimerText,
                Text::new("00:00"),
                ui.text(11.0),
                TextColor(Color::srgb(0.78, 0.95, 0.66)),
                TextLayout { justify: Justify::Center, ..default() },
                Node { position_type: PositionType::Absolute, left: px(TIMER.0), top: px(TIMER.1), width: px(TIMER.2), ..default() },
            ));
            // faction insignia = options button
            p.spawn((
                Button,
                ActivateOnPress,
                Hovered::default(),
                MenuAction::Options,
                ImageNode::new(ui.emblem(&family)),
                Node { position_type: PositionType::Absolute, left: px(INSIGNIA.0), top: px(INSIGNIA.1), width: px(INSIGNIA.2), height: px(INSIGNIA.2), ..default() },
            ));
            // radar
            let scale = (RADAR.2 / w as f32).min(RADAR.2 / h as f32);
            p.spawn(Node {
                position_type: PositionType::Absolute,
                left: px(RADAR.0),
                top: px(RADAR.1),
                width: px(RADAR.2),
                height: px(RADAR.2),
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                ..default()
            })
            .with_children(|r| {
                r.spawn((MinimapNode, RelativeCursorPosition::default(), ImageNode::new(handle), Node { width: px(w as f32 * scale), height: px(h as f32 * scale), ..default() }));
            });
            // breeding buttons, bars and the LED
            for i in 0..3 {
                p.spawn((
                    BreedButton(i),
                    Button,
                    ActivateOnPress,
                    Hovered::default(),
                    ImageNode::new(ui.button.clone()),
                    Node { position_type: PositionType::Absolute, left: px(BUTTON_X[i]), top: px(BUTTON_Y), width: px(50), height: px(50), justify_content: JustifyContent::Center, align_items: AlignItems::Center, ..default() },
                    Visibility::Hidden,
                ))
                .with_children(|b| {
                    b.spawn((BreedIcon(i), ImageNode::default(), Node { width: px(42), height: px(42), ..default() }));
                });
                p.spawn((BreedBar(i), Node { position_type: PositionType::Absolute, left: px(BAR_X[i]), top: px(BAR_Y), width: px(52), height: px(12), overflow: Overflow::clip(), ..default() }, Visibility::Hidden)).with_children(|b| {
                    b.spawn((BreedBarImage(i), ImageNode::new(ui.bar_dim.clone()), Node { position_type: PositionType::Absolute, left: px(0), top: px(0), width: px(52), height: px(12), ..default() }));
                });
            }
            p.spawn((LedNode, ImageNode::new(ui.led_off.clone()), Node { position_type: PositionType::Absolute, left: px(LED.0), top: px(LED.1), width: px(20), height: px(20), ..default() }));
            // selection screen
            p.spawn(Node {
                position_type: PositionType::Absolute,
                left: px(SELECT.0),
                top: px(SELECT.1),
                width: px(SELECT.2),
                height: px(SELECT.3),
                flex_direction: FlexDirection::Row,
                padding: UiRect::all(px(4)),
                column_gap: px(6),
                ..default()
            })
            .with_children(|sel| {
                sel.spawn((PortraitNode, ImageNode::default(), Node { width: px(86), height: px(86), flex_shrink: 0.0, ..default() }, Visibility::Hidden));
                sel.spawn(Node { flex_direction: FlexDirection::Column, row_gap: px(3), width: px(94), ..default() }).with_children(|col| {
                    col.spawn((SelNameText, Text::new(""), ui.text(12.0), TextColor(TEXT)));
                    col.spawn((HpBar, Node { width: percent(100), height: px(8), overflow: Overflow::clip(), ..default() }, BackgroundColor(Color::srgb(0.12, 0.03, 0.02)), Visibility::Hidden)).with_children(|bar| {
                        bar.spawn((HpFill, ImageNode { image: ui.bar.clone(), image_mode: NodeImageMode::Stretch, ..default() }, Node { width: percent(0), height: percent(100), ..default() }));
                    });
                    col.spawn((SelInfoText, Text::new(""), ui.text(10.0), TextColor(DIM)));
                });
            });
        });
}

/// The black message bar, the F3 statistics and the F1 help (with either sidebar).
fn spawn_overlays(commands: &mut Commands, ui: &UiAssets) {
    // black message bar at the bottom-left, like the original's command bar
    commands
        .spawn((
            DespawnOnExit(AppState::InGame),
            black_bar(ui),
            Node { position_type: PositionType::Absolute, left: px(0), bottom: px(0), width: px(MESSAGE_BAR.0), height: px(MESSAGE_BAR.1), padding: UiRect::axes(px(16), px(4)), align_items: AlignItems::Center, overflow: Overflow::clip(), ..default() },
            GlobalZIndex(5),
        ))
        .with_children(|p| {
            p.spawn((MessageText, Text::new(""), ui.text(12.0), TextColor(Color::srgb(0.95, 0.9, 0.55)), shadow()));
        });
    commands.spawn((
        DebugText,
        DespawnOnExit(AppState::InGame),
        Text::new(""),
        ui.text(13.0),
        TextColor(Color::WHITE),
        Node { position_type: PositionType::Absolute, top: px(6), left: px(6), padding: UiRect::all(px(6)), ..default() },
        BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.5)),
        Visibility::Hidden,
    ));
    commands.spawn((
        HelpText,
        DespawnOnExit(AppState::InGame),
        Text::new(HELP),
        ui.text(13.0),
        TextColor(Color::srgb(0.95, 0.95, 0.9)),
        Node { position_type: PositionType::Absolute, top: px(6), left: px(6), padding: UiRect::all(px(8)), max_width: px(760), ..default() },
        BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.7)),
        Visibility::Hidden,
    ));
}

/// The console's "select" command: selects the player's first colony; "select units" selects all
/// of the player's units (used by automated screenshots).
fn console_select(mut console: ResMut<crate::console::ConsoleState>, sim: Res<GameSim>, mut selection: ResMut<Selection>) {
    let human = sim.human_team();
    if crate::console::take_select_units_request(&mut console) {
        selection.units = sim.world.living_units().filter(|u| u.team == human).map(|u| u.id).collect();
        selection.colony = None;
    }
    if !crate::console::take_select_request(&mut console) {
        return;
    }
    if let Some(i) = sim.world.colonies.iter().position(|c| c.team == human && c.active()) {
        selection.units.clear();
        selection.colony = Some(i as u32);
    }
}

fn hud_keys(keys: Res<ButtonInput<KeyCode>>, controls: Res<Controls>, mut toggles: ResMut<HudToggles>, mut help: Query<&mut Visibility, With<HelpText>>) {
    if controls.just_pressed(&keys, "help") {
        toggles.help = !toggles.help;
        for mut v in &mut help {
            *v = if toggles.help { Visibility::Visible } else { Visibility::Hidden };
        }
    }
}

fn update_timer(sim: Res<GameSim>, mut text: Query<&mut Text, With<TimerText>>) {
    let t = sim.world.time.max(0.0) as u32;
    let s = format!("{:02}:{:02}", t / 60, t % 60);
    for mut tx in &mut text {
        if tx.0 != s {
            tx.0 = s.clone();
        }
    }
}

/// What the selected colony can breed: (model, name, build time, active).
struct BreedEntry {
    model: String,
    name: String,
    time: f32,
    active: bool,
}

/// Selected colony (own or not) with its breeding list and the progress of the active breed.
fn selected_colony(sim: &GameSim, selection: &Selection) -> Option<(u32, Vec<BreedEntry>, f32)> {
    let w = &sim.world;
    let c = selection.colony?;
    let col = w.colonies.get(c as usize)?;
    let def = w.colony_def(col);
    let mut breed = Vec::new();
    let mut progress = 0.0;
    if col.active() {
        let active = col.production.kind;
        for p in &def.produces {
            if let Some(k) = w.defs.unit(p) {
                let u = &w.defs.units[k as usize];
                let bt = w.breed_time(col.team, k, def);
                if active == Some(k) && bt > 0.0 {
                    progress = (col.production.progress / bt).clamp(0.0, 1.0);
                }
                breed.push(BreedEntry { model: u.model.clone(), name: u.name.clone(), time: bt, active: active == Some(k) });
            }
        }
    }
    Some((c, breed, progress))
}

#[allow(clippy::type_complexity)]
fn update_selection_panel(
    sim: Res<GameSim>,
    selection: Res<Selection>,
    server: Res<AssetServer>,
    mut ui: ResMut<UiAssets>,
    mut texts: ParamSet<(Query<&mut Text, With<SelNameText>>, Query<&mut Text, With<SelInfoText>>)>,
    mut nodes: ParamSet<(Query<(&mut ImageNode, &mut Visibility), With<PortraitNode>>, Query<&mut Visibility, With<HpBar>>, Query<&mut Node, With<HpFill>>)>,
) {
    let w = &sim.world;
    let mut name = String::new();
    let mut info = String::new();
    let mut hp_pct = None;
    let mut model: Option<String> = None;
    if let Some((c, breed, _)) = selected_colony(&sim, &selection) {
        let col = &w.colonies[c as usize];
        let def = w.colony_def(col);
        model = Some(def.model.clone());
        name = def.name.clone();
        hp_pct = Some((col.hp / def.hp).clamp(0.0, 1.0) * 100.0);
        match &col.state {
            ColonyState::Active => {
                info = format!("{}\n{:.0} / {:.0}", w.team_name(col.team), col.hp, def.hp);
                if let Some(b) = breed.iter().find(|b| b.active) {
                    info.push_str(&format!("\nBreeding {} ({:.0} s)", b.name, b.time));
                } else if !breed.is_empty() {
                    info.push_str("\nNot breeding");
                }
                if col.team == sim.human_team() && !breed.is_empty() {
                    let cap = if w.unit_cap() == u32::MAX { "-".to_string() } else { w.unit_cap().to_string() };
                    info.push_str(&format!("\nUnits {} / {cap}", w.team_count(col.team)));
                }
            }
            ColonyState::Defeated { launched, .. } => {
                info = if *launched { "Defeated: collect the bits!".into() } else { "Defeated".into() };
            }
        }
    } else if !selection.units.is_empty() {
        let mut counts: std::collections::BTreeMap<String, (u32, f32, f32, String)> = Default::default();
        for id in &selection.units {
            if let Some(u) = w.unit(*id) {
                let def = w.unit_def(u);
                let e = counts.entry(def.name.clone()).or_insert((0, 0.0, 0.0, def.model.clone()));
                e.0 += 1;
                e.1 += u.hp;
                e.2 += def.hp;
            }
        }
        if let Some((n, (_, hp, max, m))) = counts.iter().max_by_key(|(_, v)| v.0) {
            model = Some(m.clone());
            name = if selection.units.len() == 1 { n.clone() } else { format!("{} units", selection.units.len()) };
            hp_pct = Some(if *max > 0.0 { (hp / max).clamp(0.0, 1.0) * 100.0 } else { 0.0 });
        }
        info = counts.iter().map(|(n, v)| format!("{} x {}", v.0, n)).collect::<Vec<_>>().join("\n");
    }
    for (mut img, mut vis) in nodes.p0().iter_mut() {
        match &model {
            Some(m) => {
                let pic = ui.picture(&server, m);
                if img.image != pic {
                    img.image = pic;
                }
                *vis = Visibility::Inherited;
            }
            None => *vis = Visibility::Hidden,
        }
    }
    for mut vis in nodes.p1().iter_mut() {
        *vis = if hp_pct.is_some() { Visibility::Inherited } else { Visibility::Hidden };
    }
    for mut n in nodes.p2().iter_mut() {
        n.width = percent(hp_pct.unwrap_or(0.0));
    }
    for mut t in texts.p0().iter_mut() {
        if t.0 != name {
            t.0 = name.clone();
        }
    }
    for mut t in texts.p1().iter_mut() {
        if t.0 != info {
            t.0 = info.clone();
        }
    }
}

#[allow(clippy::type_complexity)]
fn update_breed_panel(
    sim: Res<GameSim>,
    selection: Res<Selection>,
    server: Res<AssetServer>,
    mut ui: ResMut<UiAssets>,
    mut nodes: ParamSet<(
        // not the original sidebar's buttons: they share BreedButton for its click handler, and two
        // systems setting one picture every frame made them flicker (Mike, 2026-10-14)
        Query<(&BreedButton, &Hovered, &mut ImageNode, &mut Visibility), Without<crate::orig_ui::OrigBreedIcon>>,
        Query<(&BreedIcon, &mut ImageNode)>,
        Query<(&BreedBar, &mut Node, &mut Visibility)>,
        Query<(&BreedBarImage, &mut ImageNode)>,
        Query<&mut ImageNode, With<LedNode>>,
    )>,
) {
    let selected = selected_colony(&sim, &selection);
    let (breed, progress): (&[BreedEntry], f32) = match &selected {
        Some((_, b, p)) => (b.as_slice(), *p),
        None => (&[], 0.0),
    };
    let breeding = breed.iter().any(|b| b.active);
    for (b, hovered, mut img, mut vis) in nodes.p0().iter_mut() {
        match breed.get(b.0) {
            Some(e) => {
                *vis = Visibility::Inherited;
                let want = if e.active { &ui.button_pressed } else { &ui.button };
                if img.image != *want {
                    img.image = want.clone();
                }
                let tint = if hovered.get() { Color::WHITE } else { Color::srgb(0.9, 0.9, 0.9) };
                if img.color != tint {
                    img.color = tint;
                }
            }
            None => *vis = Visibility::Hidden,
        }
    }
    for (bi, mut img) in nodes.p1().iter_mut() {
        if let Some(e) = breed.get(bi.0) {
            let pic = ui.picture(&server, &e.model);
            if img.image != pic {
                img.image = pic;
            }
        }
    }
    for (bb, mut node, mut vis) in nodes.p2().iter_mut() {
        match breed.get(bb.0) {
            Some(e) => {
                *vis = Visibility::Inherited;
                let width = if e.active { (52.0 * progress).round() } else { 52.0 };
                if node.width != px(width) {
                    node.width = px(width);
                }
            }
            None => *vis = Visibility::Hidden,
        }
    }
    for (bi, mut img) in nodes.p3().iter_mut() {
        if let Some(e) = breed.get(bi.0) {
            let want = if e.active { &ui.bar } else { &ui.bar_dim };
            if img.image != *want {
                img.image = want.clone();
            }
        }
    }
    let led = if breeding {
        &ui.led
    } else if selected.is_some() && !breed.is_empty() {
        &ui.led_red
    } else {
        &ui.led_off
    };
    for mut img in nodes.p4().iter_mut() {
        if img.image != *led {
            img.image = led.clone();
        }
    }
}

/// Observers of `Activate` run for every button, including the main menu's, where no game is
/// loaded: the simulation must stay optional here.
fn on_breed(
    ev: On<Activate>,
    buttons: Query<&BreedButton>,
    sim: Option<ResMut<GameSim>>,
    selection: Res<Selection>,
    mut messages: ResMut<Messages>,
    lib: Option<ResMut<crate::audio::AudioLibrary>>,
    mut commands: Commands,
) {
    let Ok(b) = buttons.get(ev.entity) else { return };
    let Some(mut sim) = sim else { return };
    let Some(c) = selection.colony else { return };
    let human = sim.human_team();
    let Some(col) = sim.world.colonies.get(c as usize) else { return };
    if col.team != human || !col.active() {
        return;
    }
    let def = sim.world.colony_def(col).clone();
    let Some(unit) = def.produces.get(b.0).and_then(|p| sim.world.defs.unit(p)) else { return };
    let name = sim.world.defs.units[unit as usize].name.clone();
    let stopping = col.production.kind == Some(unit);
    if stopping {
        sim.world.set_production(c, None);
        messages.push("Breeding stopped");
    } else {
        sim.world.set_production(c, Some(unit));
        messages.push(format!("Breeding {name}"));
    }
    if let Some(mut lib) = lib {
        lib.play_ui(&mut commands, if stopping { "production_stop" } else { "production_change" }, 0.8);
    }
}

fn update_minimap(sim: Res<GameSim>, cam: Option<Res<RtsCamera>>, time: Res<Time>, minimap: Option<ResMut<Minimap>>, mut images: ResMut<Assets<Image>>) {
    let Some(mut minimap) = minimap else { return };
    minimap.timer -= time.delta_secs();
    if minimap.timer > 0.0 {
        return;
    }
    minimap.timer = 0.2;
    let (w, h) = (minimap.w as i32, minimap.h as i32);
    let mut px = minimap.base.clone();
    let mut put = |x: i32, y: i32, c: [u8; 3]| {
        if x >= 0 && y >= 0 && x < w && y < h {
            let i = ((y * w + x) * 4) as usize;
            px[i] = c[0];
            px[i + 1] = c[1];
            px[i + 2] = c[2];
        }
    };
    let world = &sim.world;
    let team_color = |team: u8| -> [u8; 3] {
        let [r, g, b] = sa_sim::team_rgb(&world.teams[team as usize].def.color);
        [(r * 255.0) as u8, (g * 255.0) as u8, (b * 255.0) as u8]
    };
    for b in &world.bits {
        if b.alive {
            put(b.end.x as i32, b.end.y as i32, [255, 230, 60]);
        }
    }
    for u in world.living_units() {
        put(u.pos.x as i32, u.pos.y as i32, if u.team == 0 { [40, 40, 40] } else { team_color(u.team) });
    }
    for c in &world.colonies {
        let col = if c.active() && c.team != 0 { team_color(c.team) } else { [235, 225, 200] };
        let half = world.colony_def(c).half_extent.max(0.5) as i32;
        for dy in -half..=half {
            for dx in -half..=half {
                put(c.pos.x as i32 + dx, c.pos.y as i32 + dy, col);
            }
        }
    }
    if let Some(cam) = cam {
        let (cx, cy) = (cam.focus.x, cam.focus.z);
        let hw = (cam.distance * 0.55).max(3.0);
        let hh = (cam.distance * 0.36).max(2.0);
        let (x0, x1) = ((cx - hw) as i32, (cx + hw) as i32);
        let (y0, y1) = ((cy - hh) as i32, (cy + hh) as i32);
        for x in x0..=x1 {
            put(x, y0, [255, 255, 255]);
            put(x, y1, [255, 255, 255]);
        }
        for y in y0..=y1 {
            put(x0, y, [255, 255, 255]);
            put(x1, y, [255, 255, 255]);
        }
    }
    if let Some(mut img) = images.get_mut(&minimap.handle)
        && let Some(data) = img.data.as_mut()
    {
        *data = px;
    }
}

/// Click or drag on the minimap: the camera goes to that spot (see `orig_ui::radar_point`).
fn minimap_click(buttons: Res<ButtonInput<MouseButton>>, nodes: Query<&RelativeCursorPosition, With<MinimapNode>>, cam: Option<ResMut<RtsCamera>>, minimap: Option<Res<Minimap>>, mut held: Local<bool>) {
    if !buttons.pressed(MouseButton::Left) {
        *held = false;
        return;
    }
    let (Some(mut cam), Some(minimap)) = (cam, minimap) else { return };
    if let Some(n) = nodes.iter().find_map(|rel| rel.normalized).and_then(|n| crate::orig_ui::radar_point(n, buttons.just_pressed(MouseButton::Left), &mut held)) {
        cam.focus.x = n.x * minimap.w as f32;
        cam.focus.z = n.y * minimap.h as f32;
    }
}

fn update_messages(sim: Res<GameSim>, mode: Res<OrderMode>, time: Res<Time>, mut messages: ResMut<Messages>, mut text: Query<&mut Text, With<MessageText>>) {
    let human = sim.human_team();
    let w = &sim.world;
    for ev in &sim.events {
        match ev {
            SimEvent::ColonyCaptured { colony, team } => {
                let name = w.colonies.get(*colony as usize).map(|c| w.colony_def(c).name.clone()).unwrap_or_default();
                messages.push(if *team == human { format!("{name} captured!") } else { format!("{name} taken by {}", w.team_name(*team)) });
            }
            SimEvent::ColonyDefeated(c) => {
                let name = w.colonies.get(*c as usize).map(|c| w.colony_def(c).name.clone()).unwrap_or_default();
                messages.push(format!("{name} destroyed: collect its bits!"));
            }
            SimEvent::TeamDefeated(t) => messages.push(format!("{} defeated", w.team_name(*t))),
            _ => {}
        }
    }
    let dt = time.delta_secs();
    for l in &mut messages.lines {
        l.1 -= dt;
    }
    messages.lines.retain(|l| l.1 > 0.0);
    let mut lines: Vec<String> = Vec::new();
    if mode.attack_move {
        lines.push("Attack-move: click the destination".into());
    }
    if mode.set_rally {
        lines.push("Rally point: click a position".into());
    }
    if sim.paused {
        lines.push("PAUSED".into());
    } else if (sim.speed - 1.0).abs() > 0.01 {
        lines.push(format!("Speed x{:.2}", sim.speed));
    }
    // the bar holds two lines: the newest messages
    for l in messages.lines.iter().rev().take(2usize.saturating_sub(lines.len())) {
        lines.insert(0, l.0.clone());
    }
    let joined = lines.join("\n");
    for mut t in &mut text {
        if t.0 != joined {
            t.0 = joined.clone();
        }
    }
}

fn update_debug(mut sim: ResMut<GameSim>, dbg: Res<NavDebug>, diagnostics: Res<DiagnosticsStore>, mut text: Query<(&mut Text, &mut Visibility), With<DebugText>>, mut step_acc: Local<(f32, f32, u32)>) {
    step_acc.0 += sim.step_ms;
    sim.step_ms = 0.0;
    step_acc.2 += 1;
    if step_acc.2 >= 30 {
        step_acc.1 = step_acc.0 / step_acc.2 as f32;
        step_acc.0 = 0.0;
        step_acc.2 = 0;
    }
    let fps = diagnostics.get(&FrameTimeDiagnosticsPlugin::FPS).and_then(|d| d.smoothed()).unwrap_or(0.0);
    let w = &sim.world;
    let mut s = format!("{}   t={:>6.1}s  tick {}   x{}   fps {fps:>5.1}  sim {:.2} ms/frame", w.map.name, w.time, w.tick, sim.speed, step_acc.1);
    for t in w.teams.iter().skip(1) {
        s.push_str(&format!("\n{:<10} units {:>3}  colonies {}  kills {}  losses {}", t.def.name, t.units_alive, t.colonies, t.kills, t.losses));
    }
    let neutral = w.colonies.iter().filter(|c| !c.active() || c.team == 0).count();
    s.push_str(&format!("\nunowned structures {neutral}   bits {}   projectiles {}", w.bits.iter().filter(|b| b.alive).count(), w.projectiles.len()));
    for (mut t, mut v) in &mut text {
        t.0 = s.clone();
        *v = if dbg.0 { Visibility::Visible } else { Visibility::Hidden };
    }
}
