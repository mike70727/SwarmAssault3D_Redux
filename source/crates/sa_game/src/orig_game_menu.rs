//! The original game's in-game menu, from the player's copy: GAMEMENUBACKGROUND with the
//! casualties and colony takeovers of the four team colours, the game time in red digits, the
//! volume slider and the picture buttons (Continue or Next Level, Restart, End Game, Exit
//! Program). Esc opens it as "Game In Progress . . ."; when a level ends the spinning YOU WIN /
//! GAME OVER sign shows over the battlefield first, then the menu as "Game Over". The layout is
//! measured from the background picture and from footage of the original.
//! Used instead of menu.rs's own pause and end-of-level dialogs.

use bevy::picking::Pickable;
use bevy::prelude::*;
use bevy::state::state_scoped::DespawnOnExit;
use bevy::ui::RelativeCursorPosition;

use crate::AppState;
use crate::menu::{EndOverlay, EndState, MenuAction, PauseOverlay, PauseState};
use crate::orig_menu::{CanvasNode, abs, picture_button, rect};
use crate::orig_ui::{OrigFont, OrigUi, SidebarWidth};
use crate::settings::Settings;
use crate::sim_plugin::GameSim;

/// Size of GAMEMENUBACKGROUND.
const MENU: Vec2 = Vec2::new(576.0, 352.0);
/// Seconds the YOU WIN / GAME OVER sign shows before the menu.
const SIGN_TIME: f32 = 3.0;
/// The volume slider's track (the knob's centre runs along it).
const TRACK: Rect = Rect { min: Vec2::new(140.0, 306.0), max: Vec2::new(247.0, 330.0) };

pub struct OrigGameMenuPlugin;

impl Plugin for OrigGameMenuPlugin {
    fn build(&self, app: &mut App) {
        if !app.world().contains_resource::<OrigUi>() {
            return;
        }
        app.init_resource::<GameMenuFlow>()
            .add_systems(OnEnter(AppState::InGame), |mut f: ResMut<GameMenuFlow>| *f = GameMenuFlow::default())
            .add_systems(Update, (show_game_menu, spin_sign, volume_slider).chain().run_if(in_state(AppState::InGame)));
    }
}

/// End-of-level sequence: the sign, then the menu.
#[derive(Resource, Default)]
struct GameMenuFlow {
    sign_time: Option<f32>,
    end_menu: bool,
}

#[derive(Component)]
struct GameMenuRoot;

/// The overlay holding the sign.
#[derive(Component)]
struct SignRoot;

#[derive(Component)]
struct Sign {
    frames: Vec<Handle<Image>>,
    t: f32,
}

#[derive(Component)]
struct VolumeTrack;

#[derive(Component)]
struct VolumeKnob;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Kind {
    InProgress,
    Won { next: bool },
    Lost,
}

#[allow(clippy::too_many_arguments)]
fn show_game_menu(
    mut commands: Commands,
    pause: Res<PauseState>,
    end: Res<EndState>,
    sim: Res<GameSim>,
    mut ui: ResMut<OrigUi>,
    mut images: ResMut<Assets<Image>>,
    settings: Res<Settings>,
    sidebar: Option<Res<SidebarWidth>>,
    roots: Query<Entity, With<GameMenuRoot>>,
    signs: Query<Entity, With<SignRoot>>,
    mut flow: ResMut<GameMenuFlow>,
    time: Res<Time>,
) {
    if end.shown {
        if flow.end_menu {
            return;
        }
        let human = sim.human_team();
        let won = sim.world.winner == Some(human);
        match flow.sign_time {
            None => {
                flow.sign_time = Some(0.0);
                let frames = if won { ui.you_win.clone() } else { ui.game_over.clone() };
                let right = sidebar.map(|s| s.0).unwrap_or(0.0);
                if let Some(first) = frames.first().cloned() {
                    // over the middle of the battlefield (left of the sidebar)
                    commands
                        .spawn((
                            SignRoot,
                            EndOverlay,
                            DespawnOnExit(AppState::InGame),
                            Node { position_type: PositionType::Absolute, left: px(0), top: px(0), bottom: px(0), right: px(right), justify_content: JustifyContent::Center, align_items: AlignItems::Center, ..default() },
                            GlobalZIndex(11),
                            Pickable::IGNORE,
                        ))
                        .with_children(|p| {
                            p.spawn((CanvasNode(Vec2::new(156.0, 32.0)), Node { width: px(156), height: px(32), ..default() }, Pickable::IGNORE)).with_children(|c| {
                                c.spawn((Sign { frames, t: 0.0 }, ImageNode::new(first), abs(), rect(0.0, 0.0, 156.0, 32.0), Pickable::IGNORE));
                            });
                        });
                }
            }
            Some(t) => {
                let t = t + time.delta_secs();
                flow.sign_time = Some(t);
                if t >= SIGN_TIME {
                    for e in &signs {
                        commands.entity(e).despawn();
                    }
                    flow.end_menu = true;
                    let next = won && (sim.world.map.category == "campaign" && sim.world.map.number.is_some_and(|n| n < 100) || sim.world.map.category == "procedural");
                    let kind = if won { Kind::Won { next } } else { Kind::Lost };
                    build_menu(&mut commands, &mut ui, &mut images, &sim, kind, settings.master_volume, EndOverlay);
                }
            }
        }
        return;
    }
    if pause.open && roots.is_empty() {
        build_menu(&mut commands, &mut ui, &mut images, &sim, Kind::InProgress, settings.master_volume, PauseOverlay);
    }
}

/// The YOU WIN / GAME OVER sign turns over and over.
fn spin_sign(time: Res<Time>, mut q: Query<(&mut Sign, &mut ImageNode)>) {
    for (mut s, mut img) in &mut q {
        s.t += time.delta_secs();
        if s.frames.is_empty() {
            continue;
        }
        let f = (s.t * 12.0) as usize % s.frames.len();
        if img.image != s.frames[f] {
            img.image = s.frames[f].clone();
        }
    }
}

/// Click or drag on the slider sets the volume; the knob follows the setting.
fn volume_slider(buttons: Res<ButtonInput<MouseButton>>, tracks: Query<&RelativeCursorPosition, With<VolumeTrack>>, mut knobs: Query<&mut crate::orig_menu::CanvasRect, With<VolumeKnob>>, mut settings: ResMut<Settings>) {
    if buttons.pressed(MouseButton::Left) {
        for rel in &tracks {
            if let Some(n) = rel.normalized
                && (-0.1..=1.1).contains(&n.y)
                && (-0.05..=1.05).contains(&n.x)
            {
                let v = (n.x.clamp(0.0, 1.0) * 20.0).round() / 20.0;
                if (v - settings.master_volume).abs() > 0.001 {
                    settings.master_volume = v;
                }
            }
        }
    }
    for mut r in &mut knobs {
        let want = knob_rect(settings.master_volume).0;
        if r.0 != want {
            r.0 = want;
        }
    }
}

fn knob_rect(volume: f32) -> crate::orig_menu::CanvasRect {
    let x = TRACK.min.x + (TRACK.max.x - TRACK.min.x) * volume.clamp(0.0, 1.0);
    rect(x - 8.0, TRACK.center().y - 12.0, 16.0, 24.0)
}

/// Which of the menu's four colour rows (green, blue, red, yellow) a team's colour belongs to.
fn colour_row(color: &str) -> usize {
    let refs = [sa_sim::team_rgb("G"), sa_sim::team_rgb("B"), sa_sim::team_rgb("R"), sa_sim::team_rgb("Y")];
    let c = sa_sim::team_rgb(color);
    let d = |r: &[f32; 3]| (0..3).map(|i| (r[i] - c[i]).powi(2)).sum::<f32>();
    (0..4).min_by(|a, b| d(&refs[*a]).total_cmp(&d(&refs[*b]))).unwrap_or(0)
}

#[allow(clippy::too_many_arguments)]
fn build_menu(commands: &mut Commands, ui: &mut OrigUi, images: &mut Assets<Image>, sim: &GameSim, kind: Kind, volume: f32, marker: impl Bundle) {
    let Some(background) = ui.pic(images, "GAMEMENUBACKGROUND") else { return };
    // per colour row: casualties (units lost) and colony takeovers
    let mut rows = [(0u32, 0u32); 4];
    let mut used = [false; 4];
    for t in sim.world.teams.iter().skip(1) {
        if t.def.controller == sa_sim::Controller::None && t.losses == 0 && t.takeovers == 0 {
            continue;
        }
        // nearest free colour row
        let mut r = colour_row(&t.def.color);
        if used[r]
            && let Some(free) = (0..4).find(|i| !used[*i])
        {
            r = free;
        }
        used[r] = true;
        rows[r].0 += t.losses;
        rows[r].1 += t.takeovers;
    }
    let secs = sim.world.time.max(0.0) as u64;
    let clock = format!("{:02}:{:02}:{:02}", secs / 3600, secs / 60 % 60, secs % 60);
    let title = match kind {
        Kind::InProgress => "Game In Progress . . .",
        _ => "Game Over",
    };
    let mut label = |font: OrigFont, s: &str| ui.text(images, font, s);
    // text pieces: (image, size, x, y, centred)
    let mut texts: Vec<(Handle<Image>, Vec2, f32, f32, bool)> = Vec::new();
    let mut put = |font: OrigFont, s: &str, x: f32, y: f32, centred: bool| {
        let (h, size) = label(font, s);
        texts.push((h, size, x, y, centred));
    };
    put(OrigFont::Large, title, 288.0, 18.0, true);
    put(OrigFont::Large, "Casualties", 98.0, 62.0, true);
    put(OrigFont::Large, "Colony Takeovers", 288.0, 62.0, true);
    for (i, (lost, took)) in rows.iter().enumerate() {
        let y = 96.0 + 32.0 * i as f32;
        put(OrigFont::Digits, &lost.to_string(), 117.0, y, false);
        put(OrigFont::Digits, &took.to_string(), 310.0, y, false);
    }
    put(OrigFont::Large, "Total", 78.0, 224.0, true);
    put(OrigFont::Large, "Total", 270.0, 224.0, true);
    put(OrigFont::Digits, &rows.iter().map(|r| r.0).sum::<u32>().to_string(), 117.0, 224.0, false);
    put(OrigFont::Digits, &rows.iter().map(|r| r.1).sum::<u32>().to_string(), 310.0, 224.0, false);
    put(OrigFont::Large, "Time", 95.0, 273.0, true);
    put(OrigFont::Digits, &clock, 191.0, 273.5, true);
    put(OrigFont::Large, "Volume", 85.0, 318.0, true);
    let knob = ui.pic_keyed(images, "GAMEMENUVOLUMECONTROL");
    let first = match kind {
        Kind::InProgress => Some(("GAMEMENUCONTINUEN", "GAMEMENUCONTINUEP", MenuAction::Resume)),
        Kind::Won { next: true } => Some(("GAMEMENUNEXTLEVELN", "GAMEMENUNEXTLEVELP", MenuAction::NextLevel)),
        _ => None,
    };
    commands
        .spawn((
            GameMenuRoot,
            marker,
            DespawnOnExit(AppState::InGame),
            Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), justify_content: JustifyContent::Center, align_items: AlignItems::Center, ..default() },
            // catches clicks so they do not reach the battlefield
            BackgroundColor(Color::NONE),
            GlobalZIndex(12),
        ))
        .with_children(|root| {
            root.spawn((CanvasNode(MENU), Node { width: px(MENU.x), height: px(MENU.y), ..default() })).with_children(|c| {
                c.spawn((ImageNode::new(background), abs(), rect(0.0, 0.0, MENU.x, MENU.y)));
                for (h, size, x, y, centred) in texts {
                    let left = if centred { x - size.x * 0.5 } else { x };
                    c.spawn((ImageNode::new(h), abs(), rect(left, y - size.y * 0.5, size.x, size.y), Pickable::IGNORE));
                }
                // volume slider: the track takes the clicks, the knob shows the setting
                c.spawn((VolumeTrack, RelativeCursorPosition::default(), abs(), rect(TRACK.min.x - 8.0, TRACK.min.y, TRACK.width() + 16.0, TRACK.height())));
                if let Some(k) = knob {
                    c.spawn((VolumeKnob, ImageNode::new(k), abs(), knob_rect(volume), Pickable::IGNORE));
                }
                // the four picture buttons down the right
                let slots: [Option<(&str, &str, MenuAction)>; 4] = [
                    first,
                    Some(("GAMEMENURESTARTN", "GAMEMENURESTARTP", MenuAction::Replay)),
                    Some(("GAMEMENUENDGAMEN", "GAMEMENUENDGAMEP", MenuAction::ToMenu)),
                    Some(("GAMEMENUEXITN", "GAMEMENUEXITP", MenuAction::Quit)),
                ];
                for (i, slot) in slots.into_iter().enumerate() {
                    let r = rect(416.0, 54.0 + 48.0 * i as f32, 128.0, 32.0);
                    match slot {
                        Some((normal, pressed, action)) => picture_button(c, ui, images, normal, pressed, r, action),
                        None => {
                            if let Some(blank) = ui.pic_keyed(images, "GAMEMENUBLANKN") {
                                c.spawn((ImageNode::new(blank), abs(), r));
                            }
                        }
                    }
                }
            });
        });
}
