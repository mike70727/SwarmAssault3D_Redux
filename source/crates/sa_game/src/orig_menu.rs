//! The original game's menus, from the player's copy (orig_ui.rs): the title screen, the stone main
//! menu, the level list with its arrows, the credits and the loading screens. They keep the
//! original 640x480 layout, scaled to fit the window. Used instead of menu.rs's own menu.

use bevy::input::mouse::AccumulatedMouseScroll;
use bevy::picking::Pickable;
use bevy::picking::hover::Hovered;
use bevy::prelude::*;
use bevy::state::state_scoped::DespawnOnExit;
use bevy::ui_widgets::{Activate, ActivateOnPress, Button};
use bevy::window::PrimaryWindow;

use crate::menu::{MapEntry, MenuAction, list_maps};
use crate::orig_ui::{OrigFont, OrigUi};
use crate::progress::Progress;
use crate::settings::Settings;
use crate::{AppState, CliOptions};

/// Size of the original screens.
const CANVAS: Vec2 = Vec2::new(640.0, 480.0);
/// Rows the level list shows at once.
const ROWS: usize = 8;
/// The list box on LISTBACKGROUND (measured).
const LIST: Rect = Rect { min: Vec2::new(205.0, 120.0), max: Vec2::new(435.0, 360.0) };

pub struct OrigMenuPlugin;

impl Plugin for OrigMenuPlugin {
    fn build(&self, app: &mut App) {
        if !app.world().contains_resource::<OrigUi>() {
            return;
        }
        app.init_resource::<OrigMenu>()
            .add_systems(OnEnter(AppState::Menu), enter_menu)
            .add_systems(OnEnter(AppState::Loading), loading_screen.after(crate::sim_plugin::load_sim))
            .add_systems(Update, (layout_canvas, button_art))
            .add_systems(Update, (title_input, list_wheel, rebuild_when_needed).chain().run_if(in_state(AppState::Menu)))
            .add_observer(on_action);
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
enum Screen {
    #[default]
    Title,
    Main,
    /// the level list: campaign (false) or custom missions and skirmish maps (true)
    List(bool),
    Credits,
}

#[derive(Resource, Default)]
struct OrigMenu {
    screen: Screen,
    /// the title is shown once per run
    title_done: bool,
    scroll: usize,
    selected: usize,
    dirty: bool,
    title_time: f32,
    last_click: Option<(usize, f32)>,
}

#[derive(Component, Clone, Debug)]
enum OrigAction {
    PlayGame,
    PlayCustom,
    Credits,
    Back,
    Up,
    Down,
    Row(usize),
}

/// A node placed in the 640x480 canvas (relative to its parent node).
#[derive(Component, Clone, Copy)]
pub(crate) struct CanvasRect(pub Rect);

/// A canvas of the original screen layout: its size in original pixels, scaled like the 640x480
/// screen to fit the window.
#[derive(Component)]
pub(crate) struct CanvasNode(pub Vec2);

#[derive(Component)]
struct MenuRoot;

/// Button art: normal and pressed/hover pictures.
#[derive(Component)]
pub(crate) struct ButtonArt {
    normal: Handle<Image>,
    hover: Handle<Image>,
}

pub(crate) fn rect(x: f32, y: f32, w: f32, h: f32) -> CanvasRect {
    CanvasRect(Rect::from_corners(Vec2::new(x, y), Vec2::new(x + w, y + h)))
}

pub(crate) fn abs() -> Node {
    Node { position_type: PositionType::Absolute, ..default() }
}

/// Spawns the black full-window root with the scaled 640x480 canvas; `fill` adds the content.
fn spawn_canvas(commands: &mut Commands, state: AppState, background: Option<Handle<Image>>, fill: impl FnOnce(&mut ChildSpawnerCommands)) {
    commands
        .spawn((
            MenuRoot,
            DespawnOnExit(state),
            Node { width: percent(100), height: percent(100), justify_content: JustifyContent::Center, align_items: AlignItems::Center, ..default() },
            BackgroundColor(Color::BLACK),
            GlobalZIndex(2),
        ))
        .with_children(|root| {
            root.spawn((CanvasNode(CANVAS), Node { width: px(CANVAS.x), height: px(CANVAS.y), ..default() })).with_children(|c| {
                if let Some(bg) = background {
                    c.spawn((ImageNode::new(bg), abs(), rect(0.0, 0.0, CANVAS.x, CANVAS.y)));
                }
                fill(c);
            });
        });
}

/// A picture button (normal / pressed art from the original).
pub(crate) fn picture_button<B: Bundle>(c: &mut ChildSpawnerCommands, ui: &mut OrigUi, images: &mut Assets<Image>, normal: &str, hover: &str, r: CanvasRect, action: B) {
    let (Some(n), Some(h)) = (ui.pic_keyed(images, normal), ui.pic_keyed(images, hover)) else { return };
    c.spawn((Button, ActivateOnPress, Hovered::default(), ButtonArt { normal: n.clone(), hover: h }, ImageNode::new(n), abs(), r, action));
}

/// A blank stone button with a caption in the original font, laid on the canvas over the button.
fn caption_button<B: Bundle>(c: &mut ChildSpawnerCommands, ui: &mut OrigUi, images: &mut Assets<Image>, caption: &str, r: CanvasRect, action: B) {
    // (the original names these two without the 00 its other buttons carry)
    let (Some(n), Some(h)) = (ui.pic_keyed(images, "MAINMENUBLANKN"), ui.pic_keyed(images, "MAINMENUBLANKP")) else { return };
    let (text, size) = ui.text(images, OrigFont::Large, caption);
    let rr = r.0;
    c.spawn((Button, ActivateOnPress, Hovered::default(), ButtonArt { normal: n.clone(), hover: h }, ImageNode::new(n), abs(), r, action));
    // the large font is orange; the original's own buttons are lettered dark maroon (~98, 35, 34)
    let maroon = ImageNode { color: Color::srgb(0.53, 0.43, 1.0), ..ImageNode::new(text) };
    c.spawn((maroon, abs(), rect(rr.min.x + (rr.width() - size.x) * 0.5, rr.min.y + (rr.height() - size.y) * 0.5, size.x, size.y), Pickable::IGNORE));
}

fn enter_menu(mut menu: ResMut<OrigMenu>) {
    menu.screen = if menu.title_done { Screen::Main } else { Screen::Title };
    menu.title_time = 0.0;
    menu.dirty = true;
}

/// The entries of a level list (campaign: the unlocked levels; custom: missions, skirmish maps, demos).
fn entries(custom: bool, progress: &Progress, settings: &Settings) -> Vec<MapEntry> {
    list_maps()
        .into_iter()
        .filter(|m| if custom { m.category != "campaign" } else { m.category == "campaign" && progress.is_unlocked(m.number, settings.unlock_all_levels) })
        .collect()
}

fn entry_label(m: &MapEntry) -> String {
    match (m.category.as_str(), m.number) {
        ("campaign", Some(n)) => format!("{n:03}) {}", m.name),
        ("conquest", _) => format!("Skirmish: {}", m.name),
        ("custom", _) => format!("Mission: {}", m.name),
        _ => m.name.clone(),
    }
}

#[allow(clippy::too_many_arguments)]
fn rebuild_when_needed(
    mut commands: Commands,
    mut menu: ResMut<OrigMenu>,
    mut ui: ResMut<OrigUi>,
    mut images: ResMut<Assets<Image>>,
    roots: Query<Entity, With<MenuRoot>>,
    progress: Res<Progress>,
    settings: Res<Settings>,
) {
    if !menu.dirty {
        return;
    }
    menu.dirty = false;
    for e in &roots {
        commands.entity(e).despawn();
    }
    let ui = &mut *ui;
    let images = &mut *images;
    match menu.screen {
        Screen::Title => {
            let title = ui.title.clone();
            spawn_canvas(&mut commands, AppState::Menu, title, |_| {});
        }
        Screen::Main => {
            let bg = ui.pic(images, "MAINMENUBACKGROUND");
            // finishing the campaign opens Procedural Mode: a button of its own on the open stone under
            // the logo (the six slots of the column are engraved in the background)
            let procedural = progress.procedural_unlocked(settings.unlock_all_levels);
            spawn_canvas(&mut commands, AppState::Menu, bg, |c| {
                let slot = |i: usize| rect(224.0, 64.0 + 56.0 * i as f32, 192.0, 32.0);
                picture_button(c, ui, images, "MAINMENULOADGAMEN00", "MAINMENULOADGAMEP00", slot(0), OrigAction::PlayGame);
                picture_button(c, ui, images, "MAINMENULOADCUSTOMGAMEN00", "MAINMENULOADCUSTOMGAMEP00", slot(1), OrigAction::PlayCustom);
                caption_button(c, ui, images, "Load Saved Game", slot(2), MenuAction::LoadQuicksave);
                caption_button(c, ui, images, "Settings", slot(3), MenuAction::Settings);
                picture_button(c, ui, images, "MAINMENUCREDITSN00", "MAINMENUCREDITSP00", slot(4), OrigAction::Credits);
                picture_button(c, ui, images, "MAINMENUEXITN00", "MAINMENUEXITP00", slot(5), MenuAction::Quit);
                if procedural {
                    caption_button(c, ui, images, "Procedural Mode", rect(20.0, 204.0, 192.0, 32.0), MenuAction::StartProcedural);
                }
            });
        }
        Screen::List(custom) => {
            let list = entries(custom, &progress, &settings);
            let max_scroll = list.len().saturating_sub(ROWS);
            menu.scroll = menu.scroll.min(max_scroll);
            menu.selected = menu.selected.min(list.len().saturating_sub(1));
            if !custom && !menu.title_done {
                // first visit: start on the newest unlocked level
                menu.selected = list.len().saturating_sub(1);
                menu.scroll = menu.selected.saturating_sub(ROWS - 1).min(max_scroll);
            }
            menu.title_done = true;
            let selected_file = list.get(menu.selected).map(|m| m.file.clone());
            let bg = ui.pic(images, "LISTBACKGROUND");
            let (scroll, selected) = (menu.scroll, menu.selected);
            spawn_canvas(&mut commands, AppState::Menu, bg, |c| {
                picture_button(c, ui, images, "LISTUPN00", "LISTUPP00", rect(304.0, 64.0, 32.0, 32.0), OrigAction::Up);
                picture_button(c, ui, images, "LISTDOWNN00", "LISTDOWNP00", rect(304.0, 382.0, 32.0, 32.0), OrigAction::Down);
                picture_button(c, ui, images, "PREVIOUSN00", "PREVIOUSP00", rect(31.0, 417.0, 32.0, 32.0), OrigAction::Back);
                if let Some(file) = selected_file {
                    picture_button(c, ui, images, "NEXTN00", "NEXTP00", rect(576.0, 417.0, 32.0, 32.0), MenuAction::StartMap(file));
                }
                // the rows, clipped to the list box
                c.spawn((CanvasRect(LIST), Node { position_type: PositionType::Absolute, overflow: Overflow::clip(), ..default() })).with_children(|lb| {
                    let row_h = LIST.height() / ROWS as f32;
                    for (i, m) in list.iter().enumerate().skip(scroll).take(ROWS) {
                        let y = (i - scroll) as f32 * row_h;
                        let font = if i == selected { OrigFont::List } else { OrigFont::ListDark };
                        let (text, size) = ui.text(images, font, &entry_label(m));
                        let mut row = lb.spawn((Button, ActivateOnPress, Hovered::default(), OrigAction::Row(i), abs(), rect(0.0, y, LIST.width(), row_h)));
                        if i == selected {
                            row.insert(BackgroundColor(Color::srgba(0.95, 1.0, 0.75, 0.22)));
                        }
                        row.with_children(|r| {
                            r.spawn((ImageNode::new(text), abs(), rect(6.0, (row_h - size.y) * 0.5, size.x, size.y), Pickable::IGNORE));
                        });
                    }
                });
            });
        }
        Screen::Credits => {
            let bg = ui.pic(images, "CREDITSBACKGROUND");
            let lines: [(&str, OrigFont); 9] = [
                ("Swarm Assault", OrigFont::Large),
                ("Gate 5 Creations, 1999", OrigFont::Small),
                ("published by Mountain King Studios", OrigFont::Small),
                ("", OrigFont::Small),
                ("Swarm Assault 3D Redux", OrigFont::Large),
                ("a 3-D recreation, played with your own copy", OrigFont::Small),
                ("levels and rules after the OpenSA project", OrigFont::Small),
                ("built with Bevy and Blender", OrigFont::Small),
                ("", OrigFont::Small),
            ];
            spawn_canvas(&mut commands, AppState::Menu, bg, |c| {
                let mut y = 150.0;
                for (line, font) in lines {
                    if !line.is_empty() {
                        let (text, size) = ui.text(images, font, line);
                        c.spawn((ImageNode::new(text), abs(), rect((CANVAS.x - size.x) * 0.5, y, size.x, size.y)));
                        y += size.y + 6.0;
                    } else {
                        y += 18.0;
                    }
                }
                picture_button(c, ui, images, "PREVIOUSN00", "PREVIOUSP00", rect(31.0, 417.0, 32.0, 32.0), OrigAction::Back);
            });
        }
    }
}

fn on_action(ev: On<Activate>, actions: Query<&OrigAction>, menu: Option<ResMut<OrigMenu>>, time: Res<Time>, cli: Option<ResMut<CliOptions>>, mut next: ResMut<NextState<AppState>>, progress: Res<Progress>, settings: Res<Settings>) {
    let Ok(action) = actions.get(ev.entity) else { return };
    let Some(mut menu) = menu else { return };
    let now = time.elapsed_secs();
    match action {
        OrigAction::PlayGame => {
            menu.screen = Screen::List(false);
            menu.scroll = 0;
            menu.selected = 0;
            menu.title_done = false;
        }
        OrigAction::PlayCustom => {
            menu.screen = Screen::List(true);
            menu.scroll = 0;
            menu.selected = 0;
        }
        OrigAction::Credits => menu.screen = Screen::Credits,
        OrigAction::Back => menu.screen = Screen::Main,
        OrigAction::Up => menu.scroll = menu.scroll.saturating_sub(1),
        OrigAction::Down => menu.scroll += 1,
        OrigAction::Row(i) => {
            // a second click on the selected row starts it
            if menu.last_click.is_some_and(|(r, t)| r == *i && now - t < 0.5)
                && let Screen::List(custom) = menu.screen
                && let Some(m) = entries(custom, &progress, &settings).get(*i)
                && let Some(mut cli) = cli
            {
                cli.map = m.file.clone();
                cli.load = None;
                next.set(AppState::Loading);
                return;
            }
            menu.selected = *i;
            menu.last_click = Some((*i, now));
        }
    }
    menu.dirty = true;
}

/// The title screen gives way to the main menu on a click, a key or after a while.
fn title_input(mut menu: ResMut<OrigMenu>, time: Res<Time>, keys: Res<ButtonInput<KeyCode>>, buttons: Res<ButtonInput<MouseButton>>) {
    if menu.screen != Screen::Title {
        return;
    }
    menu.title_time += time.delta_secs();
    if menu.title_time > 6.0 || keys.get_just_pressed().next().is_some() || buttons.get_just_pressed().next().is_some() {
        menu.screen = Screen::Main;
        menu.title_done = true;
        menu.dirty = true;
    }
}

/// The mouse wheel scrolls the level list.
fn list_wheel(mut menu: ResMut<OrigMenu>, scroll: Res<AccumulatedMouseScroll>) {
    if !matches!(menu.screen, Screen::List(_)) || scroll.delta.y == 0.0 {
        return;
    }
    if scroll.delta.y > 0.0 {
        menu.scroll = menu.scroll.saturating_sub(1);
    } else {
        menu.scroll += 1;
    }
    menu.dirty = true;
}

/// The loading screen: one of the original's three pictures while the level loads.
/// A random loading picture with the level's name along its bottom bar, in the green list font
/// ("Loading . 002) Defend Your Colony", as the original).
fn loading_screen(mut commands: Commands, mut ui: ResMut<OrigUi>, mut images: ResMut<Assets<Image>>, sim: Option<Res<crate::sim_plugin::GameSim>>, time: Res<Time>) {
    commands.spawn((Camera2d, DespawnOnExit(AppState::Loading)));
    let pick = if ui.loading.is_empty() { None } else { Some(ui.loading[(time.elapsed_secs() * 1000.0) as usize % ui.loading.len()].clone()) };
    let caption = sim.map(|s| match s.world.map.number {
        Some(n) if s.world.map.category == "campaign" => format!("Loading . {n:03}) {}", s.world.map.name),
        Some(n) if s.world.map.category == "procedural" => format!("Loading . Procedural Level {n}) {}", s.world.map.name),
        _ => format!("Loading . {}", s.world.map.name),
    });
    let text = caption.map(|c| ui.text(&mut images, OrigFont::List, &c));
    spawn_canvas(&mut commands, AppState::Loading, pick, |c| {
        if let Some((h, size)) = text {
            c.spawn((ImageNode::new(h), abs(), rect(320.0 - size.x * 0.5, 459.0 - size.y * 0.5, size.x, size.y)));
        }
    });
}

/// Picture buttons show their pressed art while hovered.
fn button_art(mut q: Query<(&ButtonArt, &Hovered, &mut ImageNode)>) {
    for (art, h, mut img) in &mut q {
        let want = if h.get() { &art.hover } else { &art.normal };
        if img.image != *want {
            img.image = want.clone();
        }
    }
}

/// Scales the 640x480 canvas to fit the window and places everything on it.
fn layout_canvas(windows: Query<&Window, With<PrimaryWindow>>, mut canvases: Query<(&CanvasNode, &mut Node), Without<CanvasRect>>, mut nodes: Query<(&CanvasRect, &mut Node), Without<CanvasNode>>) {
    let Ok(window) = windows.single() else { return };
    let s = (window.width() / CANVAS.x).min(window.height() / CANVAS.y).max(0.25);
    for (canvas, mut n) in &mut canvases {
        let (w, h) = (px(canvas.0.x * s), px(canvas.0.y * s));
        if n.width != w || n.height != h {
            n.width = w;
            n.height = h;
        }
    }
    for (r, mut n) in &mut nodes {
        let (l, t, w, h) = (px(r.0.min.x * s), px(r.0.min.y * s), px(r.0.width() * s), px(r.0.height() * s));
        if n.left != l || n.top != t || n.width != w || n.height != h {
            n.left = l;
            n.top = t;
            n.width = w;
            n.height = h;
        }
    }
}
