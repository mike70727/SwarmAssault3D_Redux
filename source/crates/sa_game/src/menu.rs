//! Main menu (map list, load, quit) and the in-game pause overlay.

use bevy::app::AppExit;
use bevy::prelude::*;
use bevy::state::state_scoped::DespawnOnExit;
use bevy::ui_widgets::Activate;

use crate::progress::Progress;
use crate::selection::Selection;
use crate::settings::Settings;
use crate::sim_plugin::GameSim;
use crate::ui::{BACKDROP, DIM, GOLD, TEXT, UiAssets, dialog_button, dialog_panel, locked_button, shadow};
use crate::views::ViewIndex;
use crate::{AppState, CliOptions, asset_root};

#[derive(Component, Clone)]
pub enum MenuAction {
    StartMap(String),
    LoadQuicksave,
    Quit,
    Resume,
    SaveGame,
    LoadGame,
    ToMenu,
    /// Level list page change (+1 / -1).
    Page(i32),
    /// Load the next campaign level (end-of-level screen).
    NextLevel,
    /// Restart the current level.
    Replay,
    /// Close the end-of-level screen and keep watching.
    CloseEnd,
    /// The sidebar insignia: open the options (pause) menu.
    Options,
    /// Open the settings dialog.
    Settings,
    /// Play the current level of the procedural run (unlocked by finishing the campaign).
    StartProcedural,
    /// Download the original game's art and sound (OpenSA's way, original_download.rs); once they
    /// are in, restart the game to use them.
    GetOriginal,
}

/// End-of-level overlay (level complete / defeated).
#[derive(Component)]
pub struct EndOverlay;

#[derive(Resource, Default)]
pub struct EndState {
    pub shown: bool,
    pub timer: f32,
}

/// Extra parameters of the menu observer (Bevy systems take at most 16 parameters).
#[derive(bevy::ecs::system::SystemParam)]
struct MenuExtra<'w, 's> {
    page: ResMut<'w, MenuPage>,
    roots: Query<'w, 's, Entity, With<MenuRoot>>,
    progress: ResMut<'w, Progress>,
    settings: Res<'w, Settings>,
    end: ResMut<'w, EndState>,
    end_overlays: Query<'w, 's, Entity, With<EndOverlay>>,
    ui: Res<'w, UiAssets>,
    settings_overlays: Query<'w, 's, Entity, With<crate::settings_menu::SettingsOverlay>>,
    orig: Option<Res<'w, crate::orig_ui::OrigUi>>,
    download: Res<'w, crate::original_download::OriginalDownload>,
}

/// Root entity of the main-menu UI (rebuilt when the level page changes).
#[derive(Component)]
struct MenuRoot;

/// Current page of the level list.
#[derive(Resource, Default)]
pub struct MenuPage(pub usize);

const PAGE_SIZE: usize = 24;

#[derive(Component)]
pub struct PauseOverlay;

#[derive(Resource, Default)]
pub struct PauseState {
    pub open: bool,
}

pub struct MenuPlugin;

impl Plugin for MenuPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<PauseState>()
            .init_resource::<MenuPage>()
            .init_resource::<EndState>()
            .add_systems(OnEnter(AppState::Menu), setup_menu)
            .add_systems(OnEnter(AppState::InGame), |mut e: ResMut<EndState>| *e = EndState::default())
            .add_systems(OnExit(AppState::InGame), leave_game)
            .add_systems(Update, pause_toggle.run_if(in_state(AppState::InGame)).run_if(|c: Res<crate::console::ConsoleState>, s: Query<(), With<crate::settings_menu::SettingsOverlay>>| !c.open && s.is_empty()))
            .add_systems(Update, (game_end_screen, console_next_level, console_options).run_if(in_state(AppState::InGame)))
            .add_systems(Update, auto_start.run_if(in_state(AppState::Menu)))
            .add_observer(on_activate);
    }
}


/// One entry of the level list.
#[derive(Clone)]
pub(crate) struct MapEntry {
    pub file: String,
    pub label: String,
    /// (group, number, name): campaign levels by number, then custom missions, skirmish maps, demos.
    key: (u8, u32, String),
    pub number: Option<u32>,
    pub category: String,
    pub name: String,
}

/// Maps available in assets/data/maps, sorted for the level list.
pub(crate) fn list_maps() -> Vec<MapEntry> {
    let dir = std::path::PathBuf::from(asset_root()).join("data/maps");
    let mut out = Vec::new();
    if let Ok(rd) = std::fs::read_dir(&dir) {
        for e in rd.flatten() {
            let p = e.path();
            if p.extension().and_then(|x| x.to_str()) != Some("ron") {
                continue;
            }
            let file = p.file_name().unwrap().to_string_lossy().to_string();
            let def = std::fs::read_to_string(&p).ok().and_then(|t| sa_sim::MapDef::from_str(&t).ok());
            let Some(m) = def else {
                out.push(MapEntry { file: file.clone(), label: file.clone(), key: (4, 0, file.clone()), number: None, category: String::new(), name: file });
                continue;
            };
            let (group, number, label) = match (m.category.as_str(), m.number) {
                ("campaign", Some(n)) => (0, n, format!("{n:>3}.  {}", m.name)),
                ("custom", _) => (1, 0, format!("Custom:  {}", m.name)),
                ("conquest", _) => (2, 0, format!("Skirmish:  {}", m.name)),
                _ => (3, 0, format!("Demo:  {} ({}x{})", m.name, m.width, m.height)),
            };
            out.push(MapEntry { file, label, key: (group, number, m.name.clone()), number: if m.category == "campaign" { m.number } else { None }, category: m.category.clone(), name: m.name.clone() });
        }
    }
    out.sort_by(|a, b| a.key.cmp(&b.key));
    out
}

fn setup_menu(
    mut commands: Commands,
    page: Res<MenuPage>,
    progress: Res<Progress>,
    settings: Res<Settings>,
    ui: Res<UiAssets>,
    orig: Option<Res<crate::orig_ui::OrigUi>>,
    download: Res<crate::original_download::OriginalDownload>,
) {
    commands.spawn((Camera2d, DespawnOnExit(AppState::Menu)));
    // with the original game its own menus are used (orig_menu.rs)
    if orig.is_none() {
        build_menu(&mut commands, page.0, &progress, settings.unlock_all_levels, &ui, &download);
    }
}


/// Spawns the main-menu UI for one page of the level list: the level buttons in a stone dialog,
/// and (no copy of the original was found) the button that downloads the original's art and sound.
fn build_menu(commands: &mut Commands, page: usize, progress: &Progress, unlock_all: bool, ui: &UiAssets, download: &crate::original_download::OriginalDownload) {
    let maps = list_maps();
    let pages = maps.len().div_ceil(PAGE_SIZE).max(1);
    let page = page.min(pages - 1);
    let slice: Vec<MapEntry> = maps.iter().skip(page * PAGE_SIZE).take(PAGE_SIZE).cloned().collect();
    let rows = PAGE_SIZE / 2;
    commands
        .spawn((
            MenuRoot,
            DespawnOnExit(AppState::Menu),
            Node { width: percent(100), height: percent(100), flex_direction: FlexDirection::Column, justify_content: JustifyContent::Center, align_items: AlignItems::Center, row_gap: px(4), ..default() },
            BackgroundColor(BACKDROP),
        ))
        .with_children(|p| {
            p.spawn((Text::new("SWARM ASSAULT"), ui.text(52.0), TextColor(GOLD), shadow()));
            p.spawn((
                Text::new(format!("Campaign progress {} / 100   -   {} levels: 100 campaign, custom missions, skirmish maps", progress.completed.min(100), maps.len())),
                ui.text(14.0),
                TextColor(DIM),
                shadow(),
                Node { margin: UiRect::bottom(px(8)), ..default() },
            ));
            p.spawn(dialog_panel(ui)).with_children(|panel| {
                panel.spawn(Node { flex_direction: FlexDirection::Row, column_gap: px(8), ..default() }).with_children(|cols| {
                    for col in 0..2 {
                        cols.spawn(Node { flex_direction: FlexDirection::Column, ..default() }).with_children(|c| {
                            for entry in slice.iter().skip(col * rows).take(rows) {
                                if progress.is_unlocked(entry.number, unlock_all) {
                                    dialog_button(c, ui, &entry.label, 330.0, MenuAction::StartMap(entry.file.clone()));
                                } else {
                                    locked_button(c, ui, &format!("{}   (locked)", entry.label), 330.0);
                                }
                            }
                        });
                    }
                });
                panel.spawn(Node { flex_direction: FlexDirection::Row, align_items: AlignItems::Center, column_gap: px(8), margin: UiRect::top(px(6)), ..default() }).with_children(|nav| {
                    dialog_button(nav, ui, "< Previous page", 200.0, MenuAction::Page(-1));
                    nav.spawn((Text::new(format!("page {} / {}", page + 1, pages)), ui.text(15.0), TextColor(TEXT), shadow(), Node { width: px(120), ..default() }, TextLayout { justify: bevy::text::Justify::Center, ..default() }));
                    dialog_button(nav, ui, "Next page >", 200.0, MenuAction::Page(1));
                });
                if progress.procedural_unlocked(unlock_all) {
                    let level = if progress.procedural_seed == 0 { 1 } else { progress.procedural_level.max(1) };
                    dialog_button(panel, ui, &format!("Procedural Mode  -  level {level}"), 664.0, MenuAction::StartProcedural);
                }
                panel.spawn(Node { flex_direction: FlexDirection::Row, column_gap: px(8), ..default() }).with_children(|row| {
                    dialog_button(row, ui, "Load quicksave", 216.0, MenuAction::LoadQuicksave);
                    dialog_button(row, ui, "Settings", 216.0, MenuAction::Settings);
                    dialog_button(row, ui, "Quit", 216.0, MenuAction::Quit);
                });
                if crate::original_download::offered() {
                    crate::original_download::spawn_offer(panel, ui, download);
                }
            });
            p.spawn((
                Text::new("Left click selects, right click orders, T attack-move, Esc menu, F1 help in the game.\nLevels converted from the OpenSA re-implementation (docs/LEVELS.md)."),
                ui.text(12.0),
                TextColor(Color::srgba(0.8, 0.78, 0.7, 0.85)),
                shadow(),
                TextLayout { justify: bevy::text::Justify::Center, ..default() },
                Node { margin: UiRect::top(px(10)), ..default() },
            ));
        });
}


#[allow(clippy::too_many_arguments)]
fn on_activate(
    ev: On<Activate>,
    actions: Query<&MenuAction>,
    mut cli: ResMut<CliOptions>,
    mut next: ResMut<NextState<AppState>>,
    mut exit: MessageWriter<AppExit>,
    mut pause: ResMut<PauseState>,
    sim: Option<ResMut<GameSim>>,
    mut commands: Commands,
    overlays: Query<Entity, With<PauseOverlay>>,
    mut index: ResMut<ViewIndex>,
    mut selection: ResMut<Selection>,
    views: Query<Entity, Or<(With<crate::views::UnitView>, With<crate::views::ColonyView>, With<crate::views::BitView>, With<crate::views::ProjectileView>)>>,
    mut extra: MenuExtra,
) {
    let Ok(action) = actions.get(ev.entity) else { return };
    match action {
        MenuAction::Page(delta) => {
            let n = list_maps().len().div_ceil(PAGE_SIZE).max(1) as i32;
            extra.page.0 = (extra.page.0 as i32 + delta).rem_euclid(n) as usize;
            for r in &extra.roots {
                commands.entity(r).despawn();
            }
            build_menu(&mut commands, extra.page.0, &extra.progress, extra.settings.unlock_all_levels, &extra.ui, &extra.download);
        }
        MenuAction::GetOriginal => match extra.download.phase() {
            crate::original_download::Phase::Done(_) => {
                if crate::original_download::restart() {
                    exit.write(AppExit::Success);
                }
            }
            p if p.running() => {}
            _ => extra.download.start(),
        },
        MenuAction::StartProcedural => {
            cli.map = extra.progress.procedural_map();
            cli.load = None;
            next.set(AppState::Loading);
        }
        MenuAction::NextLevel => {
            if let Some(file) = next_level_file(sim.as_deref()) {
                cli.map = file;
                cli.load = None;
                next.set(AppState::Loading);
            } else {
                next.set(AppState::Menu);
            }
        }
        MenuAction::Replay => {
            cli.load = None;
            next.set(AppState::Loading);
        }
        MenuAction::CloseEnd => {
            for e in &extra.end_overlays {
                commands.entity(e).despawn();
            }
            extra.end.timer = f32::INFINITY;
        }
        MenuAction::StartMap(file) => {
            cli.map = file.clone();
            cli.load = None;
            next.set(AppState::Loading);
        }
        MenuAction::LoadQuicksave => {
            cli.load = Some(crate::user_path("saves/quicksave.ron").to_string_lossy().to_string());
            next.set(AppState::Loading);
        }
        MenuAction::Quit => {
            exit.write(AppExit::Success);
        }
        MenuAction::Resume => {
            close_pause(&mut commands, &overlays, &mut pause, sim);
        }
        MenuAction::SaveGame => {
            if let Some(sim) = sim.as_ref() {
                match sa_sim::save::save(&sim.world, &crate::user_path("saves/quicksave.ron")) {
                    Ok(()) => info!("saved saves/quicksave.ron"),
                    Err(e) => error!("save failed: {e}"),
                }
            }
        }
        MenuAction::LoadGame => {
            if let Some(mut sim) = sim {
                match sa_sim::save::load(&crate::user_path("saves/quicksave.ron")) {
                    Ok(w) => {
                        sim.world = w;
                        sim.events.clear();
                        selection.units.clear();
                        selection.colony = None;
                        crate::views::reset_views(&mut commands, &mut index, &views);
                        info!("loaded saves/quicksave.ron");
                        close_pause(&mut commands, &overlays, &mut pause, Some(sim));
                    }
                    Err(e) => error!("load failed: {e}"),
                }
            }
        }
        MenuAction::ToMenu => {
            close_pause(&mut commands, &overlays, &mut pause, sim);
            next.set(AppState::Menu);
        }
        MenuAction::Options => {
            if !pause.open {
                open_pause(&mut commands, &mut pause, sim, &extra.ui, extra.orig.is_some());
            }
        }
        MenuAction::Settings => {
            if extra.settings_overlays.is_empty() {
                crate::settings_menu::open_settings(&mut commands, &extra.ui, &extra.settings);
            }
        }
    }
}

fn close_pause(commands: &mut Commands, overlays: &Query<Entity, With<PauseOverlay>>, pause: &mut PauseState, sim: Option<ResMut<GameSim>>) {
    for e in overlays.iter() {
        commands.entity(e).despawn();
    }
    pause.open = false;
    if let Some(mut sim) = sim {
        sim.paused = false;
    }
}

#[allow(clippy::too_many_arguments)]
fn pause_toggle(
    mut commands: Commands,
    keys: Res<ButtonInput<KeyCode>>,
    controls: Res<crate::controls::Controls>,
    mut pause: ResMut<PauseState>,
    sim: Option<ResMut<GameSim>>,
    overlays: Query<Entity, With<PauseOverlay>>,
    ui: Res<UiAssets>,
    orig: Option<Res<crate::orig_ui::OrigUi>>,
    end: Res<EndState>,
) {
    if !controls.just_pressed(&keys, "menu") {
        return;
    }
    if pause.open {
        close_pause(&mut commands, &overlays, &mut pause, sim);
        return;
    }
    if end.shown && orig.is_some() {
        return; // the original's Game Over menu is up (or on its way)
    }
    open_pause(&mut commands, &mut pause, sim, &ui, orig.is_some());
}

/// Opens the options (pause) menu: a stone dialog over the paused game. With the original game
/// (`original`) its own in-game menu appears instead (orig_game_menu.rs builds it).
pub fn open_pause(commands: &mut Commands, pause: &mut PauseState, sim: Option<ResMut<GameSim>>, ui: &UiAssets, original: bool) {
    pause.open = true;
    if let Some(mut sim) = sim {
        sim.paused = true;
    }
    if original {
        return;
    }
    commands
        .spawn((
            PauseOverlay,
            DespawnOnExit(AppState::InGame),
            Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), justify_content: JustifyContent::Center, align_items: AlignItems::Center, ..default() },
            BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.45)),
            GlobalZIndex(10),
        ))
        .with_children(|p| {
            p.spawn(dialog_panel(ui)).with_children(|panel| {
                panel.spawn((Text::new("OPTIONS"), ui.text(30.0), TextColor(GOLD), shadow(), Node { margin: UiRect::bottom(px(10)), ..default() }));
                dialog_button(panel, ui, "Resume  (Esc)", 300.0, MenuAction::Resume);
                dialog_button(panel, ui, "Save game", 300.0, MenuAction::SaveGame);
                dialog_button(panel, ui, "Load game", 300.0, MenuAction::LoadGame);
                dialog_button(panel, ui, "Settings", 300.0, MenuAction::Settings);
                dialog_button(panel, ui, "Level select", 300.0, MenuAction::ToMenu);
                dialog_button(panel, ui, "Quit to desktop", 300.0, MenuAction::Quit);
                panel.spawn((Text::new(crate::hud::HELP), ui.text(11.0), TextColor(DIM), shadow(), Node { margin: UiRect::top(px(12)), max_width: px(640), ..default() }));
            });
        });
}

/// Automated runs (`--auto-start`): press the first level button one second after the menu opens,
/// through the same Activate event a mouse click sends.
fn auto_start(mut commands: Commands, cli: Res<CliOptions>, time: Res<Time>, buttons: Query<(Entity, &MenuAction)>, mut done: Local<bool>, mut elapsed: Local<f32>) {
    if !cli.auto_start || *done {
        return;
    }
    *elapsed += time.delta_secs();
    if *elapsed < 1.0 {
        return;
    }
    if let Some((e, _)) = buttons.iter().find(|(_, a)| matches!(a, MenuAction::StartMap(_))) {
        *done = true;
        info!("auto-start: pressing the first level button");
        commands.trigger(Activate { entity: e });
    }
}

/// File of the campaign level after the one being played, or the next procedural level (None
/// when there is none).
fn next_level_file(sim: Option<&GameSim>) -> Option<String> {
    let sim = sim?;
    if sim.world.map.category == "procedural" {
        return Some(crate::progress::procedural_map_name(sim.world.map.number? + 1, sim.world.map.run_seed?));
    }
    if sim.world.map.category != "campaign" {
        return None;
    }
    let n = sim.world.map.number? + 1;
    list_maps().into_iter().find(|m| m.category == "campaign" && m.number == Some(n)).map(|m| m.file)
}

/// Shows the level-complete / defeated screen once the game ends; records campaign progress.
#[allow(clippy::too_many_arguments)]
fn game_end_screen(
    mut commands: Commands,
    sim: Res<GameSim>,
    mut end: ResMut<EndState>,
    mut progress: ResMut<Progress>,
    mut cli: ResMut<CliOptions>,
    time: Res<Time>,
    mut next: ResMut<NextState<AppState>>,
    ui: Res<UiAssets>,
    orig: Option<Res<crate::orig_ui::OrigUi>>,
) {
    let human = sim.human_team();
    let won = sim.world.winner == Some(human);
    let lost = sim.world.teams.get(human as usize).is_some_and(|t| t.defeated) || (sim.world.game_over && !won);
    if !end.shown {
        if !(won || lost) {
            return;
        }
        end.shown = true;
        end.timer = 0.0;
        let campaign = sim.world.map.category == "campaign";
        let procedural = sim.world.map.category == "procedural";
        let number = sim.world.map.number;
        if won && campaign && let Some(n) = number {
            progress.complete(n);
        }
        if won && procedural && let (Some(n), Some(seed)) = (number, sim.world.map.run_seed) {
            progress.procedural_won(n, seed);
        }
        progress.last_level = Some(cli.map.clone());
        progress.save();
        if orig.is_some() {
            return;
        }
        let has_next = won && next_level_file(Some(&sim)).is_some();
        let title = if won { if campaign || procedural { "LEVEL COMPLETE" } else { "VICTORY" } } else { "DEFEATED" };
        let sub = match (won, campaign, number) {
            (true, true, Some(n)) if n >= 100 => "You have completed the campaign! Procedural Mode is open on the main menu.".to_string(),
            (true, false, Some(n)) if procedural => format!("Procedural level {n} won. The next one is harder."),
            (true, true, Some(n)) => format!("Level {n} won: every colony is yours and the enemy is gone."),
            (true, _, _) => "Every colony is yours and the enemy is gone.".to_string(),
            _ => "You have no colonies and no units left.".to_string(),
        };
        commands
            .spawn((
                EndOverlay,
                DespawnOnExit(AppState::InGame),
                Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), justify_content: JustifyContent::Center, align_items: AlignItems::Center, ..default() },
                BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.35)),
                GlobalZIndex(11),
            ))
            .with_children(|p| {
                p.spawn(dialog_panel(&ui)).with_children(|panel| {
                    panel.spawn((Text::new(title), ui.text(40.0), TextColor(if won { GOLD } else { Color::srgb(0.9, 0.3, 0.25) }), shadow()));
                    panel.spawn((Text::new(sub), ui.text(15.0), TextColor(TEXT), shadow(), Node { margin: UiRect::bottom(px(12)), ..default() }));
                    if has_next {
                        dialog_button(panel, &ui, "Next level", 320.0, MenuAction::NextLevel);
                    }
                    dialog_button(panel, &ui, if won { "Play again" } else { "Retry" }, 320.0, MenuAction::Replay);
                    dialog_button(panel, &ui, "Level select", 320.0, MenuAction::ToMenu);
                    dialog_button(panel, &ui, "Keep watching", 320.0, MenuAction::CloseEnd);
                });
            });
        return;
    }
    // automated runs: advance on their own after `--auto-end` seconds
    if let Some(delay) = cli.auto_end
        && end.timer.is_finite()
    {
        end.timer += time.delta_secs();
        if end.timer >= delay {
            end.timer = f32::INFINITY;
            if let Some(file) = next_level_file(Some(&sim)) {
                cli.map = file;
                cli.load = None;
                next.set(AppState::Loading);
            } else {
                next.set(AppState::Menu);
            }
        }
    }
}

/// The console's "next" command.
fn console_next_level(mut console: ResMut<crate::console::ConsoleState>, sim: Option<Res<GameSim>>, mut cli: ResMut<CliOptions>, mut next: ResMut<NextState<AppState>>) {
    if !crate::console::take_next_level_request(&mut console) {
        return;
    }
    match next_level_file(sim.as_deref()) {
        Some(file) => {
            cli.map = file;
            cli.load = None;
            next.set(AppState::Loading);
        }
        None => next.set(AppState::Menu),
    }
}

/// The console's "options" command (also used by automated screenshots).
fn console_options(mut commands: Commands, mut console: ResMut<crate::console::ConsoleState>, mut pause: ResMut<PauseState>, sim: Option<ResMut<GameSim>>, ui: Res<UiAssets>, orig: Option<Res<crate::orig_ui::OrigUi>>) {
    if crate::console::take_options_request(&mut console) && !pause.open {
        open_pause(&mut commands, &mut pause, sim, &ui, orig.is_some());
    }
}

/// Leaving the game: drop the simulation and view bookkeeping (entities are state-scoped).
fn leave_game(mut commands: Commands, mut index: ResMut<ViewIndex>, mut selection: ResMut<Selection>, mut pause: ResMut<PauseState>) {
    commands.remove_resource::<GameSim>();
    commands.remove_resource::<crate::camera::RtsCamera>();
    index.units.clear();
    index.colonies.clear();
    index.bits.clear();
    index.projectiles.clear();
    index.generation += 1;
    selection.units.clear();
    selection.colony = None;
    pause.open = false;
}
