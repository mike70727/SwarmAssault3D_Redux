//! The original interface, read from the player's copy of the original game (see original.rs):
//! the stone sidebar with its emblem, name plates, breeding buttons, the 3-D portraits of the
//! selected creature, the red progress bar and the radar; the original cursors; bitmap fonts for
//! the menus. Used instead of the game's own interface (hud.rs, ui.rs) when the original is found.
//!
//! The sidebar keeps the original's 160x480 layout and is scaled to the window height.

use std::collections::HashMap;

use bevy::asset::RenderAssetUsages;
use bevy::image::ImageSampler;
use bevy::picking::hover::Hovered;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};
use bevy::state::state_scoped::DespawnOnExit;
use bevy::ui::RelativeCursorPosition;
use bevy::ui_widgets::{ActivateOnPress, Button};
use bevy::window::PrimaryWindow;

use crate::AppState;
use crate::camera::RtsCamera;
use crate::hud::BreedButton;
use crate::menu::MenuAction;
use crate::original::{Original, OriginalGame, Rgba};
use crate::selection::Selection;
use crate::sim_plugin::GameSim;

/// Size of the original sidebar in its own pixels.
pub const PANEL: Vec2 = Vec2::new(160.0, 480.0);

pub struct OrigUiPlugin;

impl Plugin for OrigUiPlugin {
    fn build(&self, app: &mut App) {
        // built while the app is built: the first state (menu or level) may need it at once
        let original = app.world().resource::<Original>().clone();
        let Some(orig) = original.0.clone() else { return };
        let ui = {
            let mut images = app.world_mut().resource_mut::<Assets<Image>>();
            OrigUi::build(orig, &mut images)
        };
        info!("original interface loaded: {} pictures", ui.count);
        app.insert_resource(ui)
            .add_systems(OnEnter(AppState::InGame), setup_sidebar.after(crate::ground::spawn_ground))
            .add_systems(Update, (layout_panel, update_sidebar, update_radar, radar_click).run_if(in_state(AppState::InGame)));
    }
}

// ---- pictures --------------------------------------------------------------------------------

fn image(p: &Rgba, nearest: bool) -> Image {
    let mut img = Image::new(
        Extent3d { width: p.w, height: p.h, depth_or_array_layers: 1 },
        TextureDimension::D2,
        p.px.clone(),
        TextureFormat::Rgba8UnormSrgb,
        RenderAssetUsages::default(),
    );
    img.sampler = if nearest { ImageSampler::nearest() } else { ImageSampler::linear() };
    img
}

/// Pure black made transparent (the original drew these sprites with black as the colour key).
fn keyed(mut p: Rgba) -> Rgba {
    for px in p.px.chunks_exact_mut(4) {
        if px[0] < 6 && px[1] < 6 && px[2] < 6 {
            px[3] = 0;
        }
    }
    p
}

/// A glyph of a bitmap font, trimmed to its opaque columns.
#[derive(Clone)]
struct Glyph {
    pic: Rgba,
}

/// The original's bitmap fonts.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum OrigFont {
    /// green menu-list font (Start.DDF S_*)
    List,
    /// the same, darker (the highlighted entry)
    ListDark,
    /// large orange font (MLFONTLARGED)
    Large,
    /// large yellow-orange font (MLFONTLARGEL)
    LargeLight,
    /// small blue font (MLFONTSMALL)
    Small,
    /// red digital digits of the game menu's numbers and clock (B_0..B_9, B_COLON)
    Digits,
}

/// Glyph name suffixes of the Start.DDF fonts (S_ / SX_ prefixes).
fn list_glyph_name(c: char) -> Option<String> {
    let s = match c {
        'A'..='Z' => c.to_string(),
        'a'..='z' => {
            let u = c.to_ascii_uppercase();
            format!("{u}{u}")
        }
        '0'..='9' => c.to_string(),
        '!' => "EXCL".into(),
        '"' => "DQUOTE".into(),
        '#' => "HASH".into(),
        '$' => "DOLLAR".into(),
        '%' => "PERCENT".into(),
        '&' => "AND".into(),
        '\'' => "SQUOTE".into(),
        '(' => "RBL".into(),
        ')' => "RBR".into(),
        '*' => "STAR".into(),
        '+' => "PLUS".into(),
        ',' => "COMMA".into(),
        '-' => "MINUS".into(),
        '.' => "FULLSTOP".into(),
        '/' => "FSLASH".into(),
        ':' => "COLON".into(),
        ';' => "SEMICOLON".into(),
        '<' => "LESSTHAN".into(),
        '=' => "EQUAL".into(),
        '>' => "GREATERTHAN".into(),
        '?' => "QUESTION".into(),
        '@' => "AT".into(),
        '[' => "SBL".into(),
        '\\' => "BSLASH".into(),
        ']' => "SBR".into(),
        '^' => "HAT".into(),
        '_' => "USCORE".into(),
        '`' => "APOS".into(),
        '{' => "CBL".into(),
        '|' => "PIPE".into(),
        '}' => "CBR".into(),
        '~' => "SQUIG".into(),
        _ => return None,
    };
    Some(s)
}

fn trim_columns(p: &Rgba) -> Rgba {
    let col_used = |x: u32| (0..p.h).any(|y| p.px[((y * p.w + x) * 4 + 3) as usize] > 0);
    let x0 = (0..p.w).find(|&x| col_used(x));
    let x1 = (0..p.w).rev().find(|&x| col_used(x));
    match (x0, x1) {
        (Some(a), Some(b)) => p.crop(a, 0, b - a + 1, p.h),
        _ => Rgba::new((p.w / 3).max(2), p.h),
    }
}

fn load_font(orig: &OriginalGame, font: OrigFont) -> HashMap<char, Glyph> {
    let mut out = HashMap::new();
    match font {
        OrigFont::List | OrigFont::ListDark => {
            let prefix = if font == OrigFont::List { "S_" } else { "SX_" };
            for c in (32u8..127).map(|b| b as char) {
                if let Some(n) = list_glyph_name(c)
                    && let Some(p) = orig.picture(&format!("{prefix}{n}"))
                {
                    out.insert(c, Glyph { pic: keyed(p) });
                }
            }
        }
        OrigFont::Digits => {
            // kept full width so the clock's digits stay put
            for c in "0123456789:!".chars() {
                let n = match c {
                    ':' => "COLON".to_string(),
                    '!' => "EXCL".to_string(),
                    d => d.to_string(),
                };
                if let Some(p) = orig.picture(&format!("B_{n}")) {
                    let p = keyed(p);
                    out.insert(c, Glyph { pic: if c == ':' { trim_columns(&p) } else { p } });
                }
            }
        }
        OrigFont::Large | OrigFont::LargeLight | OrigFont::Small => {
            let prefix = match font {
                OrigFont::Large => "MLFONTLARGED",
                OrigFont::LargeLight => "MLFONTLARGEL",
                _ => "MLFONTSMALL",
            };
            for code in 33u32..=254 {
                if let Some(p) = orig.picture(&format!("{prefix}{:03}", code - 32))
                    && let Some(c) = char::from_u32(code)
                {
                    out.insert(c, Glyph { pic: trim_columns(&keyed(p)) });
                }
            }
        }
    }
    out
}

/// Everything of the original interface, ready as Bevy images.
#[derive(Resource)]
pub struct OrigUi {
    pub count: usize,
    pub panel: Handle<Image>,
    /// MIEMBLEM00..03: yellow, red, green, blue
    pub emblems: Vec<Handle<Image>>,
    pub progress: Vec<Handle<Image>>,
    /// mouse cursors: name -> frames (normal, select, move, attack, selecttemp)
    pub cursors: HashMap<&'static str, Vec<Handle<Image>>>,
    pub game_over: Vec<Handle<Image>>,
    pub you_win: Vec<Handle<Image>>,
    /// loading screens (Game\Loading0N.DDF) and the title screen (Start\SwarmAssaultLogo.DDF)
    pub loading: Vec<Handle<Image>>,
    pub title: Option<Handle<Image>>,
    /// any other picture, decoded on first use (name plates, portraits, breeding icons, menus)
    pics: HashMap<String, Handle<Image>>,
    fonts: HashMap<OrigFont, HashMap<char, Glyph>>,
    /// the pictures that exist (so a lookup can answer without decoding)
    names: std::collections::HashSet<String>,
    source: std::sync::Arc<OriginalGame>,
}

impl OrigUi {
    fn build(source: std::sync::Arc<OriginalGame>, images: &mut Assets<Image>) -> Self {
        let orig: &OriginalGame = &source;
        let mut count = 0;
        let mut add = |p: Rgba, nearest: bool| {
            count += 1;
            images.add(image(&p, nearest))
        };
        let panel = add(orig.picture("MIGPANEL00").unwrap_or_else(|| Rgba::new(160, 480)), false);
        let emblems = (0..4).map(|i| add(keyed(orig.picture(&format!("MIEMBLEM{i:02}")).unwrap_or_else(|| Rgba::new(82, 82))), false)).collect();
        let progress = (0..32).filter_map(|i| orig.picture(&format!("COLONYPROGRESS{i:02}"))).map(|p| add(p, false)).collect();
        let mut cursors = HashMap::new();
        for (key, prefix) in [("normal", "MOUSENORMAL"), ("select", "MOUSESELECT"), ("move", "MOUSEMOVE"), ("attack", "MOUSEATTACK"), ("selecttemp", "MOUSESELECTTEMP")] {
            let frames: Vec<_> = (0..3).filter_map(|i| orig.picture(&format!("{prefix}{i:02}"))).map(|p| add(keyed(p), true)).collect();
            if !frames.is_empty() {
                cursors.insert(key, frames);
            }
        }
        let game_over = (0..10).filter_map(|i| orig.picture(&format!("GAMEOVER{i:02}"))).map(|p| add(keyed(p), false)).collect();
        let you_win = (0..10).filter_map(|i| orig.picture(&format!("GAMEOVERWIN{i:02}"))).map(|p| add(keyed(p), false)).collect();
        let loading = orig.loading.iter().map(|p| add(p.clone(), false)).collect();
        let title = orig.title.clone().map(|p| add(p, false));
        let mut fonts = HashMap::new();
        for f in [OrigFont::List, OrigFont::ListDark, OrigFont::Large, OrigFont::LargeLight, OrigFont::Small, OrigFont::Digits] {
            fonts.insert(f, load_font(orig, f));
        }
        let mut names: std::collections::HashSet<String> = orig.game.names().map(|s| s.to_string()).collect();
        if let Some(s) = &orig.start {
            names.extend(s.names().map(|s| s.to_string()));
        }
        Self { count, panel, emblems, progress, cursors, game_over, you_win, loading, title, pics: HashMap::new(), fonts, names, source }
    }

    pub fn has(&self, name: &str) -> bool {
        self.names.contains(name)
    }

    /// A picture of the original game as an image (decoded once).
    pub fn pic(&mut self, images: &mut Assets<Image>, name: &str) -> Option<Handle<Image>> {
        if let Some(h) = self.pics.get(name) {
            return Some(h.clone());
        }
        if !self.has(name) {
            return None;
        }
        let p = self.source.picture(name)?;
        let h = images.add(image(&p, false));
        self.pics.insert(name.to_string(), h.clone());
        Some(h)
    }

    /// A picture with black made transparent.
    pub fn pic_keyed(&mut self, images: &mut Assets<Image>, name: &str) -> Option<Handle<Image>> {
        let key = format!("{name}#keyed");
        if let Some(h) = self.pics.get(&key) {
            return Some(h.clone());
        }
        let p = keyed(self.source.picture(name)?);
        let h = images.add(image(&p, false));
        self.pics.insert(key, h.clone());
        Some(h)
    }

    /// Text drawn with one of the original's bitmap fonts (native size; scale it with the UI).
    pub fn text_picture(&self, font: OrigFont, text: &str) -> Rgba {
        let glyphs = &self.fonts[&font];
        let height = glyphs.values().map(|g| g.pic.h).max().unwrap_or(16);
        let space = (height / 3).max(3);
        let gap = if matches!(font, OrigFont::List | OrigFont::ListDark | OrigFont::Digits) { 0 } else { 1 };
        let width: u32 = text.chars().map(|c| glyphs.get(&c).map(|g| g.pic.w + gap).unwrap_or(space)).sum::<u32>().max(1);
        let mut out = Rgba::new(width, height);
        let mut x = 0i32;
        for c in text.chars() {
            match glyphs.get(&c) {
                Some(g) => {
                    out.blit(&g.pic, x, (height - g.pic.h) as i32);
                    x += (g.pic.w + gap) as i32;
                }
                None => x += space as i32,
            }
        }
        out
    }

    /// Text as an image handle (cached by font and text).
    pub fn text(&mut self, images: &mut Assets<Image>, font: OrigFont, text: &str) -> (Handle<Image>, Vec2) {
        let key = format!("text#{font:?}#{text}");
        let pic = self.text_picture(font, text);
        let size = Vec2::new(pic.w as f32, pic.h as f32);
        if let Some(h) = self.pics.get(&key) {
            return (h.clone(), size);
        }
        let h = images.add(image(&pic, true));
        self.pics.insert(key, h.clone());
        (h, size)
    }
}

// ---- names of the original pictures ------------------------------------------------------------

/// Family code, tier letter and name-plate key of a unit model (`None` for unknown models).
pub fn unit_codes(model: &str) -> Option<(&'static str, &'static str, &'static str)> {
    Some(match model {
        "ant_soldier" => ("ANT", "A", "SOLDIER"),
        "ant_grenadier" => ("ANT", "B", "GRENADIER"),
        "ant_bazooka" => ("ANT", "C", "BAZOOKA"),
        "beetle_ladybug" => ("BEETLE", "A", "LADYBUG"),
        "beetle_shrapnel" => ("BEETLE", "B", "SHRAPNEL"),
        "beetle_cannon" => ("BEETLE", "C", "CANNON"),
        "spider_black_widow" => ("SPIDER", "A", "BLACKWIDOW"),
        "spider_sniper" => ("SPIDER", "B", "SNIPER"),
        "spider_missile" => ("SPIDER", "C", "ROCKET"),
        "scorpion_savage" => ("SCORPION", "A", "SAVAGE"),
        "scorpion_spear_gun" => ("SCORPION", "B", "SPEARGUN"),
        "scorpion_ninja" => ("SCORPION", "C", "NINJA"),
        "wasp_assault" => ("WASP", "A", "ASSAULT"),
        "wasp_paralysis" => ("WASP", "B", "PARALYSIS"),
        "wasp_sonic" => ("WASP", "C", "SONIC"),
        "neutral_bull_ant" => ("NEUTRAL", "", "ANTBULL"),
        "neutral_pirate_grenadier" => ("NEUTRAL", "", "ANTGRENADIER"),
        "neutral_dragonfly" => ("NEUTRAL", "", "DRAGONFLY"),
        "neutral_desert_fly" => ("NEUTRAL", "", "FLY"),
        "neutral_spawn_moth" => ("NEUTRAL", "", "MOTH"),
        "neutral_flying_machine" => ("NEUTRAL", "", "FLYINGMACHINE"),
        // creep plants (NAMENEUTRAL<key> plates and COLONYNEUTRAL<key>3D portraits)
        "plant_popcorn" => ("NEUTRAL", "", "POPCORN"),
        "plant_thorn" => ("NEUTRAL", "", "THORNBUSH"),
        "plant_seedball" | "plant_seed" => ("NEUTRAL", "", "SEEDBALL"),
        "plant_freckle" => ("NEUTRAL", "", "FRECKLE"),
        "plant_lolly_blue" | "plant_lolly_orange" | "plant_lolly_white" | "plant_lolly_red" => ("NEUTRAL", "", "LOLLY"),
        _ => return None,
    })
}

/// Family code of a colony model.
pub fn colony_code(model: &str) -> Option<&'static str> {
    Some(match model {
        "colony_ant" => "ANT",
        "colony_beetle" => "BEETLE",
        "colony_spider" => "SPIDER",
        "colony_scorpion" => "SCORPION",
        "colony_wasp" => "WASP",
        _ => return None,
    })
}

/// The original team colour letter (Y, R, G, B) nearest to a team colour.
pub fn team_letter(color: &str) -> char {
    let [r, g, b] = sa_sim::team_rgb(color);
    let refs = [('Y', [0.91, 0.77, 0.28]), ('R', [0.79, 0.19, 0.19]), ('G', [0.34, 0.67, 0.29]), ('B', [0.31, 0.50, 0.82])];
    refs.iter()
        .min_by(|a, b2| {
            let d = |c: [f32; 3]| (c[0] - r).powi(2) + (c[1] - g).powi(2) + (c[2] - b).powi(2);
            d(a.1).total_cmp(&d(b2.1))
        })
        .map(|x| x.0)
        .unwrap_or('Y')
}

fn emblem_index(letter: char) -> usize {
    match letter {
        'R' => 1,
        'G' => 2,
        'B' => 3,
        _ => 0,
    }
}

// ---- the sidebar ---------------------------------------------------------------------------------

/// Where a sidebar element sits, in the original panel's pixels.
#[derive(Component, Clone, Copy)]
struct PanelRect(Rect);

#[derive(Component)]
struct OrigSidebar;
#[derive(Component)]
struct OrigEmblem;
#[derive(Component)]
struct OrigName(u8);
#[derive(Component)]
struct OrigPortrait;
#[derive(Component)]
struct OrigProgress;
#[derive(Component)]
struct OrigBreedIcon(usize);
#[derive(Component)]
struct OrigRadarNode;

/// Width of the sidebar on screen (input and edge panning stop there).
#[derive(Resource, Clone, Copy)]
pub struct SidebarWidth(pub f32);

impl Default for SidebarWidth {
    fn default() -> Self {
        Self(crate::ui::SIDEBAR_WIDTH)
    }
}

/// Panel slots, measured on MIGPANEL00.
const EMBLEM: Rect = Rect { min: Vec2::new(39.0, 6.0), max: Vec2::new(121.0, 88.0) };
const NAME1: Rect = Rect { min: Vec2::new(16.0, 96.0), max: Vec2::new(144.0, 114.0) };
const BREED_X: [f32; 3] = [21.0, 60.0, 99.0];
const BREED_Y: f32 = 118.0;
const PORTRAIT: Rect = Rect { min: Vec2::new(16.0, 168.0), max: Vec2::new(144.0, 232.0) };
const NAME2: Rect = Rect { min: Vec2::new(16.0, 239.0), max: Vec2::new(144.0, 257.0) };
const PROGRESS: Rect = Rect { min: Vec2::new(16.0, 267.0), max: Vec2::new(144.0, 283.0) };
const RADAR: Rect = Rect { min: Vec2::new(16.0, 336.0), max: Vec2::new(144.0, 464.0) };

/// The radar picture: terrain colours per cell, redrawn with units, colonies and the view.
#[derive(Resource)]
struct OrigRadar {
    handle: Handle<Image>,
    w: u32,
    h: u32,
    base: Vec<u8>,
    timer: f32,
}

fn rect_node(r: Rect) -> (Node, PanelRect) {
    (Node { position_type: PositionType::Absolute, ..default() }, PanelRect(r))
}

#[allow(clippy::too_many_arguments)]
fn setup_sidebar(
    mut commands: Commands,
    sim: Res<GameSim>,
    mut ui: ResMut<OrigUi>,
    mut images: ResMut<Assets<Image>>,
    radar_base: Option<Res<crate::ground::RadarBase>>,
) {
    let human = sim.human_team();
    let letter = sim.world.teams.get(human as usize).map(|t| team_letter(&t.def.color)).unwrap_or('Y');
    // the radar: terrain colours from the 3-D ground (one pixel per cell)
    let (w, h) = (sim.world.grid.w as u32, sim.world.grid.h as u32);
    let base = radar_base.map(|r| r.rgba.clone()).unwrap_or_else(|| vec![60; (w * h * 4) as usize]);
    let mut radar_img = Image::new(Extent3d { width: w, height: h, depth_or_array_layers: 1 }, TextureDimension::D2, base.clone(), TextureFormat::Rgba8UnormSrgb, RenderAssetUsages::MAIN_WORLD | RenderAssetUsages::RENDER_WORLD);
    radar_img.sampler = ImageSampler::nearest();
    let radar = images.add(radar_img);
    commands.insert_resource(OrigRadar { handle: radar.clone(), w, h, base, timer: 0.0 });
    // the radar keeps the map's aspect inside its square
    let fit = (RADAR.width() / w as f32).min(RADAR.height() / h as f32);
    let (rw, rh) = (w as f32 * fit, h as f32 * fit);
    let radar_rect = Rect::from_center_size(RADAR.center(), Vec2::new(rw, rh));

    let empty = Handle::<Image>::default();
    commands
        .spawn((
            OrigSidebar,
            DespawnOnExit(AppState::InGame),
            Node { position_type: PositionType::Absolute, top: px(0), right: px(0), height: percent(100), ..default() },
            BackgroundColor(Color::srgb(0.07, 0.06, 0.05)),
            GlobalZIndex(5),
        ))
        .with_children(|p| {
            let (n, r) = rect_node(Rect { min: Vec2::ZERO, max: PANEL });
            p.spawn((ImageNode::new(ui.panel.clone()), n, r));
            let (n, r) = rect_node(EMBLEM);
            p.spawn((OrigEmblem, Button, ActivateOnPress, Hovered::default(), MenuAction::Options, ImageNode::new(ui.emblems[emblem_index(letter)].clone()), n, r));
            for (i, slot) in [NAME1, NAME2].into_iter().enumerate() {
                let (n, r) = rect_node(slot);
                p.spawn((OrigName(i as u8), ImageNode::new(empty.clone()), n, r, Visibility::Hidden));
            }
            for (i, x) in BREED_X.iter().enumerate() {
                let (n, r) = rect_node(Rect { min: Vec2::new(*x, BREED_Y), max: Vec2::new(*x + 40.0, BREED_Y + 40.0) });
                p.spawn((BreedButton(i), OrigBreedIcon(i), Button, ActivateOnPress, Hovered::default(), ImageNode::new(empty.clone()), n, r, Visibility::Hidden));
            }
            let (n, r) = rect_node(PORTRAIT);
            p.spawn((OrigPortrait, ImageNode::new(empty.clone()), n, r, Visibility::Hidden));
            let (n, r) = rect_node(PROGRESS);
            p.spawn((OrigProgress, ImageNode::new(ui.progress.first().cloned().unwrap_or_default()), n, r, Visibility::Hidden));
            let (n, r) = rect_node(radar_rect);
            p.spawn((OrigRadarNode, RelativeCursorPosition::default(), ImageNode::new(radar), n, r));
        });
    // name plates of every creature are cheap: decode them now so selection changes are instant
    let _ = ui.pic(&mut images, "NAMEBLANK");
}

/// Scales the sidebar to the window height (the original panel is 480 pixels tall).
fn layout_panel(windows: Query<&Window, With<PrimaryWindow>>, mut width: ResMut<SidebarWidth>, mut roots: Query<&mut Node, (With<OrigSidebar>, Without<PanelRect>)>, mut nodes: Query<(&PanelRect, &mut Node), Without<OrigSidebar>>, mut last: Local<f32>) {
    let Ok(window) = windows.single() else { return };
    let s = (window.height() / PANEL.y).max(0.5);
    if (s - *last).abs() < 1e-3 && !nodes.is_empty() && roots.iter().all(|n| n.width != Val::Auto) {
        return;
    }
    *last = s;
    width.0 = PANEL.x * s;
    for mut n in &mut roots {
        n.width = px(PANEL.x * s);
    }
    for (r, mut n) in &mut nodes {
        n.left = px(r.0.min.x * s);
        n.top = px(r.0.min.y * s);
        n.width = px(r.0.width() * s);
        n.height = px(r.0.height() * s);
    }
}

/// What the selection shows: name plates, portrait, breeding buttons, progress.
#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn update_sidebar(
    sim: Res<GameSim>,
    selection: Res<Selection>,
    mut ui: ResMut<OrigUi>,
    mut images: ResMut<Assets<Image>>,
    mut q: ParamSet<(
        Query<(&OrigName, &mut ImageNode, &mut Visibility)>,
        Query<(&mut ImageNode, &mut Visibility), With<OrigPortrait>>,
        Query<(&OrigBreedIcon, &Hovered, &mut ImageNode, &mut Visibility)>,
        Query<(&mut ImageNode, &mut Visibility), With<OrigProgress>>,
    )>,
) {
    let w = &sim.world;
    let human = sim.human_team();
    let mut names: [Option<String>; 2] = [None, None];
    let mut portrait: Option<String> = None;
    let mut breed: Vec<(String, bool)> = Vec::new();
    let mut progress: Option<f32> = None;
    if let Some(c) = selection.colony
        && let Some(col) = w.colonies.get(c as usize)
    {
        let def = w.colony_def(col);
        if let Some(fam) = colony_code(&def.model) {
            names[0] = Some(format!("NAME{fam}COLONY"));
            let letter = w.teams.get(col.team as usize).map(|t| team_letter(&t.def.color)).unwrap_or('Y');
            if col.active() {
                let active = col.production.kind;
                for p in &def.produces {
                    if let Some(k) = w.defs.unit(p) {
                        let u = &w.defs.units[k as usize];
                        if let Some((f, tier, key)) = unit_codes(&u.model) {
                            let on = active == Some(k);
                            if col.team == human {
                                breed.push((format!("COLONY{f}{tier}{}", if on { "01" } else { "00" }), on));
                            }
                            if on {
                                names[1] = Some(format!("NAME{f}{key}"));
                                portrait = Some(format!("COLONY{f}{tier}3D{letter}"));
                                let bt = u.build_time * def.build_time_multiplier * w.team_production_mult(col.team);
                                progress = Some(if bt > 0.0 { (col.production.progress / bt).clamp(0.0, 1.0) } else { 0.0 });
                            }
                        }
                    }
                }
                if progress.is_none() && col.team != human {
                    progress = Some((col.hp / def.hp).clamp(0.0, 1.0));
                }
            }
        }
    } else if !selection.units.is_empty() {
        // the most numerous creature of the selection
        let mut counts: HashMap<&str, (u32, f32, f32, u8)> = HashMap::new();
        for id in &selection.units {
            if let Some(u) = w.unit(*id) {
                let def = w.unit_def(u);
                let e = counts.entry(def.model.as_str()).or_insert((0, 0.0, 0.0, u.team));
                e.0 += 1;
                e.1 += u.hp;
                e.2 += def.hp;
            }
        }
        if let Some((model, (_, hp, max, team))) = counts.iter().max_by_key(|(_, v)| v.0)
            && let Some((fam, tier, key)) = unit_codes(model)
        {
            let letter = w.teams.get(*team as usize).map(|t| team_letter(&t.def.color)).unwrap_or('Y');
            names[0] = Some(format!("NAME{fam}UNIT"));
            names[1] = Some(format!("NAME{fam}{key}"));
            portrait = Some(if fam == "NEUTRAL" { format!("COLONYNEUTRAL{key}3D") } else { format!("COLONY{fam}{tier}3D{letter}") });
            progress = Some(if *max > 0.0 { (hp / max).clamp(0.0, 1.0) } else { 0.0 });
        }
    }
    for (n, mut img, mut vis) in q.p0().iter_mut() {
        match names[n.0 as usize].as_deref().and_then(|name| ui.pic(&mut images, name)) {
            Some(h) => {
                if img.image != h {
                    img.image = h;
                }
                *vis = Visibility::Inherited;
            }
            None => *vis = Visibility::Hidden,
        }
    }
    for (mut img, mut vis) in q.p1().iter_mut() {
        match portrait.as_deref().and_then(|name| ui.pic(&mut images, name)) {
            Some(h) => {
                if img.image != h {
                    img.image = h;
                }
                *vis = Visibility::Inherited;
            }
            None => *vis = Visibility::Hidden,
        }
    }
    for (b, hovered, mut img, mut vis) in q.p2().iter_mut() {
        match breed.get(b.0).and_then(|(name, _)| ui.pic(&mut images, name)) {
            Some(h) => {
                if img.image != h {
                    img.image = h;
                }
                img.color = if hovered.get() { Color::srgb(1.15, 1.15, 1.15) } else { Color::WHITE };
                *vis = Visibility::Inherited;
            }
            None => *vis = Visibility::Hidden,
        }
    }
    let frames = ui.progress.clone();
    for (mut img, mut vis) in q.p3().iter_mut() {
        match progress {
            Some(f) if !frames.is_empty() => {
                let i = ((f * (frames.len() - 1) as f32).round() as usize).min(frames.len() - 1);
                if img.image != frames[i] {
                    img.image = frames[i].clone();
                }
                *vis = Visibility::Inherited;
            }
            _ => *vis = Visibility::Hidden,
        }
    }
}

/// The radar: terrain, colonies, units and the camera's view, redrawn five times a second.
fn update_radar(sim: Res<GameSim>, cam: Option<Res<RtsCamera>>, time: Res<Time>, radar: Option<ResMut<OrigRadar>>, mut images: ResMut<Assets<Image>>, cameras: Query<(&Camera, &GlobalTransform), With<crate::camera::MainCamera>>) {
    let Some(mut radar) = radar else { return };
    radar.timer -= time.delta_secs();
    if radar.timer > 0.0 {
        return;
    }
    radar.timer = 0.2;
    let (w, h) = (radar.w as i32, radar.h as i32);
    let mut px = radar.base.clone();
    let mut put = |x: i32, y: i32, c: [u8; 3]| {
        if x >= 0 && y >= 0 && x < w && y < h {
            let i = ((y * w + x) * 4) as usize;
            px[i..i + 3].copy_from_slice(&c);
        }
    };
    let world = &sim.world;
    let team_color = |team: u8| -> [u8; 3] {
        if team == 0 {
            return [20, 20, 20];
        }
        let [r, g, b] = sa_sim::team_rgb(&world.teams[team as usize].def.color);
        [(r * 255.0) as u8, (g * 255.0) as u8, (b * 255.0) as u8]
    };
    for c in &world.colonies {
        let col = if c.active() { team_color(c.team) } else { [235, 225, 200] };
        let half = world.colony_def(c).half_extent.max(0.5) as i32;
        for dy in -half..half {
            for dx in -half..half {
                put(c.pos.x as i32 + dx, c.pos.y as i32 + dy, col);
            }
        }
    }
    for b in &world.bits {
        if b.alive {
            put(b.end.x as i32, b.end.y as i32, [255, 230, 60]);
        }
    }
    for u in world.living_units() {
        let c = team_color(u.team);
        put(u.pos.x as i32, u.pos.y as i32, c);
        put(u.pos.x as i32 + 1, u.pos.y as i32, c);
    }
    // the camera's view on the ground: the four screen corners projected onto the map
    if cam.is_some()
        && let Ok((camera, tf)) = cameras.single()
        && let Some(vp) = camera.logical_viewport_size()
    {
        let corners = [Vec2::new(0.0, 0.0), Vec2::new(vp.x, 0.0), Vec2::new(vp.x, vp.y), Vec2::new(0.0, vp.y)];
        let pts: Vec<Vec2> = corners.iter().filter_map(|c| crate::camera::cursor_ground_point(camera, tf, *c)).collect();
        if pts.len() == 4 {
            for i in 0..4 {
                let (a, b) = (pts[i], pts[(i + 1) % 4]);
                let steps = (a.distance(b) * 1.5).ceil().max(1.0) as i32;
                for s in 0..=steps {
                    let p = a.lerp(b, s as f32 / steps as f32);
                    put(p.x as i32, p.y as i32, [255, 255, 255]);
                }
            }
        }
    }
    if let Some(mut img) = images.get_mut(&radar.handle)
        && let Some(data) = img.data.as_mut()
    {
        *data = px;
    }
}

/// Click or drag on the radar: the camera goes to that spot, as in the original.  Only a press
/// that starts on the radar counts (a selection box dragged over the sidebar does not move the
/// camera); dragging on from there follows the cursor, held at the radar's edge.
fn radar_click(buttons: Res<ButtonInput<MouseButton>>, nodes: Query<&RelativeCursorPosition, With<OrigRadarNode>>, cam: Option<ResMut<RtsCamera>>, radar: Option<Res<OrigRadar>>, mut held: Local<bool>) {
    if !buttons.pressed(MouseButton::Left) {
        *held = false;
        return;
    }
    let (Some(mut cam), Some(radar)) = (cam, radar) else { return };
    if let Some(n) = nodes.iter().find_map(|rel| rel.normalized).and_then(|n| radar_point(n, buttons.just_pressed(MouseButton::Left), &mut held)) {
        cam.focus.x = n.x * radar.w as f32;
        cam.focus.z = n.y * radar.h as f32;
    }
}

/// The map point (0..1 across the picture) of a press on a radar picture.  Bevy measures
/// `RelativeCursorPosition` from the node's centre, -0.5..0.5 (it was 0..1 from the corner before
/// 0.15, which left only the radar's bottom-right quarter clickable).  `held` remembers whether the
/// press began on the radar.
pub fn radar_point(centred: Vec2, just_pressed: bool, held: &mut bool) -> Option<Vec2> {
    let n = centred + Vec2::splat(0.5);
    if just_pressed {
        *held = (0.0..=1.0).contains(&n.x) && (0.0..=1.0).contains(&n.y);
    }
    held.then(|| n.clamp(Vec2::ZERO, Vec2::ONE))
}

#[cfg(test)]
mod radar_tests {
    use super::*;

    #[test]
    fn radar_press_maps_the_whole_picture() {
        let mut held = false;
        // a press at the top-left corner, the centre and the bottom-right corner of the picture
        assert_eq!(radar_point(Vec2::new(-0.5, -0.5), true, &mut held), Some(Vec2::ZERO));
        assert_eq!(radar_point(Vec2::ZERO, true, &mut held), Some(Vec2::splat(0.5)));
        assert_eq!(radar_point(Vec2::new(0.5, 0.5), true, &mut held), Some(Vec2::ONE));
        // dragging on past the edge holds the edge
        assert_eq!(radar_point(Vec2::new(0.9, -0.25), false, &mut held), Some(Vec2::new(1.0, 0.25)));
        // a press that starts off the radar never moves the camera, even when it is dragged onto it
        assert_eq!(radar_point(Vec2::new(-3.0, 0.0), true, &mut held), None);
        assert_eq!(radar_point(Vec2::new(0.1, 0.1), false, &mut held), None);
    }
}
