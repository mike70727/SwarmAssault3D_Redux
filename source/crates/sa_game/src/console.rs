//! In-game console (Enter opens a text bar) and the cheat menu it unlocks with the word "cheat".

use bevy::input::ButtonState;
use bevy::input::keyboard::{Key, KeyboardInput};
use bevy::prelude::*;
use bevy::state::state_scoped::DespawnOnExit;
use bevy::ui_widgets::Activate;

use crate::AppState;
use crate::camera::RtsCamera;
use crate::controls::Controls;
use crate::hud::Messages;
use crate::menu::PauseState;
use crate::progress::Progress;
use crate::sim_plugin::GameSim;
use crate::ui::{GOLD, UiAssets, black_bar, dialog_button, dialog_panel, shadow};

#[derive(Resource, Default)]
pub struct ConsoleState {
    pub open: bool,
    pub buffer: String,
    pub menu: bool,
    /// Set by the "next" command: the menu's next-level action is triggered on the next frame.
    pub request_next_level: bool,
    /// Set by the "options" command: the options dialog opens on the next frame.
    pub request_options: bool,
    /// Set by the "select" command: the player's first colony gets selected on the next frame.
    pub request_select: bool,
    /// Set by "select units": every unit of the player gets selected (automated screenshots).
    pub request_select_units: bool,
    /// Set by the "settings" command: the settings dialog opens on the next frame.
    pub request_settings: bool,
}

#[derive(Component)]
struct ConsoleBar;
#[derive(Component)]
struct ConsoleText;
#[derive(Component)]
struct CheatMenu;

#[derive(Component, Clone, Copy)]
enum CheatAction {
    Win,
    UnlockAll,
    God,
    FastBreed,
    NoCap,
    Heal,
    CaptureAll,
    KillEnemies,
    Spawn,
    Close,
}

pub struct ConsolePlugin;

impl Plugin for ConsolePlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<ConsoleState>()
            .add_systems(OnEnter(AppState::InGame), setup_console)
            .add_systems(OnExit(AppState::InGame), |mut c: ResMut<ConsoleState>| {
                c.open = false;
                c.menu = false;
                c.buffer.clear();
            })
            .add_systems(Update, (console_keys, console_auto, console_bar, cheat_menu_sync, console_settings).run_if(in_state(AppState::InGame)))
            .add_observer(on_cheat);
    }
}

fn setup_console(mut commands: Commands, ui: Res<UiAssets>) {
    // the console types into a second black bar above the message bar
    commands
        .spawn((
            ConsoleBar,
            DespawnOnExit(AppState::InGame),
            black_bar(&ui),
            Node { position_type: PositionType::Absolute, left: px(0), bottom: px(50), width: px(520), height: px(46), padding: UiRect::axes(px(16), px(4)), align_items: AlignItems::Center, ..default() },
            Visibility::Hidden,
            GlobalZIndex(8),
        ))
        .with_children(|p| {
            p.spawn((ConsoleText, Text::new("> "), ui.text(14.0), TextColor(Color::srgb(0.95, 0.9, 0.6)), shadow()));
        });
}

#[allow(clippy::too_many_arguments)]
fn console_keys(
    keys: Res<ButtonInput<KeyCode>>,
    controls: Res<Controls>,
    mut input: MessageReader<KeyboardInput>,
    mut console: ResMut<ConsoleState>,
    pause: Res<PauseState>,
    mut sim: ResMut<GameSim>,
    mut messages: ResMut<Messages>,
    mut progress: ResMut<Progress>,
    cam: Option<Res<RtsCamera>>,
) {
    if !console.open {
        input.clear();
        if !pause.open && controls.just_pressed(&keys, "console") {
            console.open = true;
            console.buffer.clear();
        }
        return;
    }
    let mut run: Option<String> = None;
    for ev in input.read() {
        if ev.state != ButtonState::Pressed {
            continue;
        }
        match &ev.logical_key {
            Key::Enter => run = Some(console.buffer.trim().to_string()),
            Key::Escape => {
                console.open = false;
                console.buffer.clear();
            }
            Key::Backspace => {
                console.buffer.pop();
            }
            Key::Space => console.buffer.push(' '),
            Key::Character(c) => {
                if console.buffer.len() < 60 {
                    console.buffer.push_str(c);
                }
            }
            _ => {}
        }
    }
    let Some(line) = run else { return };
    console.open = false;
    console.buffer.clear();
    run_command(&line, &mut console, &mut sim, &mut messages, &mut progress, cam.as_deref());
}

/// Automated runs: execute `--console-cmd` once, 3 s into the level.
fn console_auto(cli: Res<crate::CliOptions>, sim: Option<ResMut<GameSim>>, mut console: ResMut<ConsoleState>, mut messages: ResMut<Messages>, mut progress: ResMut<Progress>, cam: Option<Res<RtsCamera>>, mut done: Local<bool>) {
    let (Some(cmd), Some(mut sim)) = (cli.console_cmd.clone(), sim) else { return };
    if *done || sim.world.time < 3.0 {
        return;
    }
    *done = true;
    // several commands can be chained with ';' (e.g. "spawn 8;march 25 0")
    for c in cmd.split(';') {
        run_command(c, &mut console, &mut sim, &mut messages, &mut progress, cam.as_deref());
    }
}

fn run_command(line: &str, console: &mut ConsoleState, sim: &mut GameSim, messages: &mut Messages, progress: &mut Progress, cam: Option<&RtsCamera>) {
    let line = line.trim();
    if line.is_empty() {
        return;
    }
    let human = sim.human_team();
    let mut words = line.split_whitespace();
    let cmd = words.next().unwrap_or("").to_lowercase();
    let arg = words.next().map(|s| s.to_string());
    match cmd.as_str() {
        "cheat" | "cheats" => console.menu = true,
        "help" | "?" => messages.push("commands: cheat, win, unlock, god, fast, nocap, heal, capture, kill, spawn [n], next, select, options, settings, march [dx dy]"),
        "win" => {
            sim.world.cheat_win(human);
            messages.push("Cheat: level won");
        }
        "unlock" => {
            progress.unlocked_all = true;
            progress.save();
            messages.push("Cheat: all levels unlocked");
        }
        "god" => {
            let on = sim.world.cheats.invincible != Some(human);
            sim.world.cheats.invincible = if on { Some(human) } else { None };
            messages.push(if on { "Cheat: your units and colonies are invincible" } else { "Invincibility off" });
        }
        "fast" => {
            let on = sim.world.cheats.fast_breed.is_none();
            sim.world.cheats.fast_breed = if on { Some((human, 10.0)) } else { None };
            messages.push(if on { "Cheat: breeding 10x faster" } else { "Fast breeding off" });
        }
        "nocap" => {
            sim.world.cheats.no_cap = !sim.world.cheats.no_cap;
            let on = sim.world.cheats.no_cap;
            messages.push(if on { "Cheat: no unit cap" } else { "Unit cap restored" });
        }
        "heal" => {
            sim.world.cheat_heal(human);
            messages.push("Cheat: everything healed");
        }
        "capture" => {
            sim.world.cheat_capture_all(human);
            messages.push("Cheat: every colony is yours");
        }
        "kill" => {
            sim.world.cheat_kill_enemies(human);
            messages.push("Cheat: all enemy units destroyed");
        }
        "spawn" => {
            let n = arg.and_then(|a| a.parse::<u32>().ok()).unwrap_or(10).clamp(1, 200);
            spawn_units(sim, human, cam, n, messages);
        }
        "next" => console.request_next_level = true,
        "options" | "menu" => console.request_options = true,
        "select" if arg.as_deref() == Some("units") => console.request_select_units = true,
        "select" => console.request_select = true,
        "settings" => console.request_settings = true,
        "march" => {
            // every own unit walks by (dx, dy) cells from the group's centre (facing/animation checks)
            let dx = arg.and_then(|a| a.parse::<f32>().ok()).unwrap_or(20.0);
            let dy = words.next().and_then(|a| a.parse::<f32>().ok()).unwrap_or(0.0);
            let ids: Vec<_> = sim.world.living_units().filter(|u| u.team == human && sim.world.unit_def(u).controllable).map(|u| u.id).collect();
            if ids.is_empty() {
                messages.push("march: no units");
            } else {
                let centre = ids.iter().filter_map(|id| sim.world.unit(*id)).map(|u| u.pos).sum::<sa_sim::Vec2>() / ids.len() as f32;
                let target = sim.world.grid.clamp(centre + sa_sim::Vec2::new(dx, dy));
                sim.world.issue(&ids, sa_sim::world::Order::Move(target));
                messages.push(format!("march: {} units to ({:.0}, {:.0})", ids.len(), target.x, target.y));
            }
        }
        _ => messages.push(format!("Unknown command '{cmd}' (type help)")),
    }
}

fn spawn_units(sim: &mut GameSim, team: u8, cam: Option<&RtsCamera>, n: u32, messages: &mut Messages) {
    // the light unit of the team's first colony, or an ant soldier
    let kind = sim
        .world
        .colonies
        .iter()
        .find(|c| c.team == team && c.active())
        .and_then(|c| sim.world.colony_def(c).produces.first().cloned())
        .and_then(|p| sim.world.defs.unit(&p))
        .or_else(|| sim.world.defs.unit("ant_soldier"));
    let Some(kind) = kind else { return };
    let pos = cam.map(|c| Vec2::new(c.focus.x, c.focus.z)).unwrap_or(sim.world.grid.size() * 0.5);
    let pos = sim.world.grid.clamp(pos);
    sim.world.cheat_spawn(kind, team, pos, n);
    messages.push(format!("Cheat: {n} units spawned"));
}

fn console_bar(console: Res<ConsoleState>, mut bar: Query<&mut Visibility, With<ConsoleBar>>, mut text: Query<&mut Text, With<ConsoleText>>) {
    for mut v in &mut bar {
        *v = if console.open { Visibility::Visible } else { Visibility::Hidden };
    }
    for mut t in &mut text {
        t.0 = format!("> {}_", console.buffer);
    }
}

fn build_cheat_menu(commands: &mut Commands, sim: &GameSim, progress: &Progress, ui: &UiAssets) {
    let human = sim.human_team();
    let on = |b: bool| if b { "ON" } else { "OFF" };
    commands
        .spawn((
            CheatMenu,
            DespawnOnExit(AppState::InGame),
            Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), justify_content: JustifyContent::Center, align_items: AlignItems::Center, ..default() },
            BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.45)),
            GlobalZIndex(12),
        ))
        .with_children(|p| {
            p.spawn(dialog_panel(ui)).with_children(|panel| {
                panel.spawn((Text::new("CHEATS"), ui.text(30.0), TextColor(GOLD), shadow(), Node { margin: UiRect::bottom(px(8)), ..default() }));
                dialog_button(panel, ui, "Win this level", 360.0, CheatAction::Win);
                dialog_button(panel, ui, &format!("Unlock all levels: {}", on(progress.unlocked_all)), 360.0, CheatAction::UnlockAll);
                dialog_button(panel, ui, &format!("Invincible units and colonies: {}", on(sim.world.cheats.invincible == Some(human))), 360.0, CheatAction::God);
                dialog_button(panel, ui, &format!("Breed 10x faster: {}", on(sim.world.cheats.fast_breed.is_some())), 360.0, CheatAction::FastBreed);
                dialog_button(panel, ui, &format!("No unit cap: {}", on(sim.world.cheats.no_cap)), 360.0, CheatAction::NoCap);
                dialog_button(panel, ui, "Heal all my units and colonies", 360.0, CheatAction::Heal);
                dialog_button(panel, ui, "Capture every colony", 360.0, CheatAction::CaptureAll);
                dialog_button(panel, ui, "Destroy all enemy units", 360.0, CheatAction::KillEnemies);
                dialog_button(panel, ui, "Spawn 10 units at the camera", 360.0, CheatAction::Spawn);
                dialog_button(panel, ui, "Close", 360.0, CheatAction::Close);
            });
        });
}

fn cheat_menu_sync(mut commands: Commands, console: Res<ConsoleState>, sim: Res<GameSim>, progress: Res<Progress>, menus: Query<Entity, With<CheatMenu>>, mut shown: Local<bool>, ui: Res<UiAssets>) {
    if console.menu && !*shown {
        build_cheat_menu(&mut commands, &sim, &progress, &ui);
        *shown = true;
    } else if !console.menu && *shown {
        for e in &menus {
            commands.entity(e).despawn();
        }
        *shown = false;
    }
}

#[allow(clippy::too_many_arguments)]
fn on_cheat(
    ev: On<Activate>,
    actions: Query<&CheatAction>,
    mut commands: Commands,
    mut console: ResMut<ConsoleState>,
    sim: Option<ResMut<GameSim>>,
    mut progress: ResMut<Progress>,
    mut messages: ResMut<Messages>,
    cam: Option<Res<RtsCamera>>,
    menus: Query<Entity, With<CheatMenu>>,
    ui: Res<UiAssets>,
) {
    // runs for every button activation, including the main menu's: no game may be loaded
    let Ok(action) = actions.get(ev.entity) else { return };
    let Some(mut sim) = sim else { return };
    let human = sim.human_team();
    match action {
        CheatAction::Win => {
            sim.world.cheat_win(human);
            messages.push("Cheat: level won");
        }
        CheatAction::UnlockAll => {
            progress.unlocked_all = !progress.unlocked_all;
            progress.save();
            messages.push(if progress.unlocked_all { "Cheat: all levels unlocked" } else { "Levels unlock in order again" });
        }
        CheatAction::God => {
            let on = sim.world.cheats.invincible != Some(human);
            sim.world.cheats.invincible = if on { Some(human) } else { None };
            messages.push(if on { "Cheat: invincible" } else { "Invincibility off" });
        }
        CheatAction::FastBreed => {
            let on = sim.world.cheats.fast_breed.is_none();
            sim.world.cheats.fast_breed = if on { Some((human, 10.0)) } else { None };
            messages.push(if on { "Cheat: breeding 10x faster" } else { "Fast breeding off" });
        }
        CheatAction::NoCap => {
            sim.world.cheats.no_cap = !sim.world.cheats.no_cap;
            let on = sim.world.cheats.no_cap;
            messages.push(if on { "Cheat: no unit cap" } else { "Unit cap restored" });
        }
        CheatAction::Heal => {
            sim.world.cheat_heal(human);
            messages.push("Cheat: everything healed");
        }
        CheatAction::CaptureAll => {
            sim.world.cheat_capture_all(human);
            messages.push("Cheat: every colony is yours");
        }
        CheatAction::KillEnemies => {
            sim.world.cheat_kill_enemies(human);
            messages.push("Cheat: all enemy units destroyed");
        }
        CheatAction::Spawn => spawn_units(&mut sim, human, cam.as_deref(), 10, &mut messages),
        CheatAction::Close => {}
    }
    // rebuild the menu so the ON/OFF labels are current (or close it)
    for e in &menus {
        commands.entity(e).despawn();
    }
    if matches!(action, CheatAction::Close) {
        console.menu = false;
    } else {
        build_cheat_menu(&mut commands, &sim, &progress, &ui);
    }
}

/// Used by the menu plugin to trigger "next level" from the console.
pub fn take_next_level_request(console: &mut ConsoleState) -> bool {
    std::mem::take(&mut console.request_next_level)
}

pub fn take_options_request(console: &mut ConsoleState) -> bool {
    std::mem::take(&mut console.request_options)
}

pub fn take_select_request(console: &mut ConsoleState) -> bool {
    std::mem::take(&mut console.request_select)
}

pub fn take_select_units_request(console: &mut ConsoleState) -> bool {
    std::mem::take(&mut console.request_select_units)
}

/// Forwards the "settings" command to the settings dialog.
pub fn console_settings(mut console: ResMut<ConsoleState>, mut request: ResMut<crate::settings_menu::SettingsRequest>) {
    if std::mem::take(&mut console.request_settings) {
        request.0 = true;
    }
}
