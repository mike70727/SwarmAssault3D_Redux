//! Procedural levels: the endless "Procedural Mode" that finishing the campaign unlocks. Every level
//! is a new map made from a seed, a little harder than the one before.
//!
//! The ground is laid with the original's own ground templates (48x48-pixel pictures covering 2x2
//! cells). What the generator knows about them it learns from the converted original levels
//! (`MapDef::tiles` and `cells`): which templates each tileset has, what terrain each quarter is,
//! how often each is used and which may sit to the right of and below which. A wave-function-
//! collapse fill, steered by a smooth terrain plan (lakes, rock, scrub) and kept clear around the
//! colonies, then gives shores and outcrops shaped like the original's.

use std::collections::BTreeMap;
use std::path::Path;

use glam::Vec2;
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;

use crate::data::{ColonySpawn, Controller, CreepPool, DataError, Defs, MapDef, MapRules, Obstacle, TeamDef, UnitSpawn};

// ---- template sets -------------------------------------------------------------------------------

/// A set of template ids (0..=255).
type Bits = [u64; 4];

const NONE: Bits = [0; 4];

fn bit(t: u8) -> Bits {
    let mut b = NONE;
    b[(t >> 6) as usize] = 1 << (t & 63);
    b
}

fn has(b: &Bits, t: u8) -> bool {
    b[(t >> 6) as usize] >> (t & 63) & 1 == 1
}

fn union(a: &mut Bits, b: &Bits) {
    for i in 0..4 {
        a[i] |= b[i];
    }
}

fn inter(a: &Bits, b: &Bits) -> Bits {
    [a[0] & b[0], a[1] & b[1], a[2] & b[2], a[3] & b[3]]
}

fn count(b: &Bits) -> u32 {
    b.iter().map(|w| w.count_ones()).sum()
}

fn members(b: &Bits) -> impl Iterator<Item = u8> + '_ {
    (0..4usize).flat_map(move |i| {
        let mut w = b[i];
        std::iter::from_fn(move || {
            if w == 0 {
                return None;
            }
            let t = w.trailing_zeros();
            w &= w - 1;
            Some((i as u32 * 64 + t) as u8)
        })
    })
}

// ---- what the original levels teach --------------------------------------------------------------

/// Terrain kinds in `MapDef::cells` order of the arrays below.
const KINDS: [u8; 4] = [b'.', b'r', b'v', b'w'];
const CLEAR: usize = 0;
const WATER: usize = 3;

fn kind_index(c: u8) -> usize {
    KINDS.iter().position(|k| *k == c).unwrap_or(CLEAR)
}

#[derive(Clone, Debug, Default)]
struct PropStat {
    count: u32,
    radius: f32,
    scale: f32,
    blocking: u32,
}

#[derive(Clone, Debug, Default)]
struct CreepStat {
    levels: u32,
    counts: Vec<u32>,
    interval: (f32, f32),
    first: (f32, f32),
}

/// What one tileset's levels look like.
#[derive(Clone, Debug)]
pub struct TileModel {
    /// templates seen in the levels
    all: Bits,
    /// blocks laid with each template
    weight: Vec<f32>,
    /// per template and quarter: cells of each terrain kind, and the most common one
    quarter_kinds: Vec<[[u32; 4]; 4]>,
    kinds: Vec<[usize; 4]>,
    /// right[a]: templates seen to the right of `a`; down[a] below it; left and up the inverse
    right: Vec<Bits>,
    down: Vec<Bits>,
    left: Vec<Bits>,
    up: Vec<Bits>,
    /// cells of each terrain kind in the levels
    cells: [u64; 4],
    props: BTreeMap<String, PropStat>,
    creeps: BTreeMap<String, CreepStat>,
    /// number of levels and their mean area in cells
    pub levels: u32,
    area: f64,
}

impl Default for TileModel {
    fn default() -> Self {
        Self {
            all: NONE,
            weight: vec![0.0; 256],
            quarter_kinds: vec![[[0; 4]; 4]; 256],
            kinds: vec![[CLEAR; 4]; 256],
            right: vec![NONE; 256],
            down: vec![NONE; 256],
            left: vec![NONE; 256],
            up: vec![NONE; 256],
            cells: [0; 4],
            props: BTreeMap::new(),
            creeps: BTreeMap::new(),
            levels: 0,
            area: 0.0,
        }
    }
}

impl TileModel {
    /// Terrain kind of quarter `q` of template `t` (the most common one in the levels).
    fn kind(&self, t: u8, q: usize) -> usize {
        self.kinds[t as usize][q]
    }

    fn all_clear(&self, t: u8) -> bool {
        (0..4).all(|q| self.kind(t, q) == CLEAR)
    }

    /// Share of the cells of terrain kind `k`.
    fn share(&self, k: usize) -> f32 {
        let n: u64 = self.cells.iter().sum();
        if n == 0 { 0.0 } else { self.cells[k] as f32 / n as f32 }
    }
}

/// Ground templates, props and creeps of the four tilesets, learned from the converted levels.
#[derive(Clone, Debug, Default)]
pub struct GroundModel {
    pub tilesets: BTreeMap<String, TileModel>,
}

/// Per-cell (template, quarter) codes of a `tiles` string (whitespace ignored).
fn parse_tiles(text: &str) -> Vec<(u8, u8)> {
    let chars: Vec<u8> = text.bytes().filter(|c| !c.is_ascii_whitespace()).collect();
    chars
        .chunks_exact(3)
        .map(|c| {
            let hex = |s: &[u8]| std::str::from_utf8(s).ok().and_then(|s| u8::from_str_radix(s, 16).ok()).unwrap_or(0);
            (hex(&c[0..2]), hex(&c[2..3]))
        })
        .collect()
}

impl GroundModel {
    /// Learns from every map that has an original ground layout.
    pub fn learn<'a>(maps: impl IntoIterator<Item = &'a MapDef>) -> Self {
        let mut model = GroundModel::default();
        for map in maps {
            let (Some(tiles), Some(cells)) = (&map.tiles, &map.cells) else { continue };
            let (w, h) = (map.width as usize, map.height as usize);
            let codes = parse_tiles(tiles);
            let kinds: Vec<u8> = cells.bytes().filter(|c| !c.is_ascii_whitespace()).collect();
            if codes.len() != w * h || kinds.len() != w * h {
                continue;
            }
            let tm = model.tilesets.entry(map.tileset.clone()).or_default();
            tm.levels += 1;
            tm.area += (w * h) as f64;
            // the 2x2 blocks: find the grid offset the level's templates sit on
            let (ox, oy) = [(0, 0), (1, 0), (0, 1), (1, 1)]
                .into_iter()
                .max_by_key(|(ox, oy)| (0..w * h).filter(|i| codes[*i].1 as usize == ((i / w + 2 - oy) % 2) * 2 + (i % w + 2 - ox) % 2).count())
                .unwrap_or((0, 0));
            let (bw, bh) = ((w - ox) / 2, (h - oy) / 2);
            let mut blocks: Vec<Option<u8>> = vec![None; bw * bh];
            for by in 0..bh {
                for bx in 0..bw {
                    let at = |dx: usize, dy: usize| (oy + by * 2 + dy) * w + ox + bx * 2 + dx;
                    let quads = [at(0, 0), at(1, 0), at(0, 1), at(1, 1)];
                    let t = codes[quads[0]].0;
                    if quads.iter().enumerate().all(|(q, i)| codes[*i] == (t, q as u8)) {
                        blocks[by * bw + bx] = Some(t);
                        union(&mut tm.all, &bit(t));
                        tm.weight[t as usize] += 1.0;
                        for (q, i) in quads.iter().enumerate() {
                            tm.quarter_kinds[t as usize][q][kind_index(kinds[*i])] += 1;
                        }
                    }
                }
            }
            for by in 0..bh {
                for bx in 0..bw {
                    let Some(a) = blocks[by * bw + bx] else { continue };
                    if bx + 1 < bw && let Some(b) = blocks[by * bw + bx + 1] {
                        union(&mut tm.right[a as usize], &bit(b));
                        union(&mut tm.left[b as usize], &bit(a));
                    }
                    if by + 1 < bh && let Some(b) = blocks[(by + 1) * bw + bx] {
                        union(&mut tm.down[a as usize], &bit(b));
                        union(&mut tm.up[b as usize], &bit(a));
                    }
                }
            }
            for k in &kinds {
                tm.cells[kind_index(*k)] += 1;
            }
            for o in &map.obstacles {
                let p = tm.props.entry(o.kind.clone()).or_default();
                p.count += 1;
                p.radius += o.radius;
                p.scale += o.scale;
                p.blocking += o.blocking as u32;
            }
            for pool in &map.rules.creeps {
                let c = tm.creeps.entry(pool.units.join(",")).or_default();
                c.levels += 1;
                c.counts.push(pool.count);
                c.interval = pool.interval;
                c.first = pool.first;
            }
        }
        for tm in model.tilesets.values_mut() {
            if tm.levels > 0 {
                tm.area /= tm.levels as f64;
            }
            for t in 0..256 {
                for q in 0..4 {
                    let c = &tm.quarter_kinds[t][q];
                    tm.kinds[t][q] = (0..4).max_by_key(|k| (c[*k], 3 - *k)).unwrap_or(CLEAR);
                }
            }
        }
        model
    }

    /// Learns from every level file in `dir` (assets/data/maps).
    pub fn from_dir(dir: &Path) -> Result<Self, DataError> {
        let mut paths: Vec<_> = std::fs::read_dir(dir)?.filter_map(|e| e.ok()).map(|e| e.path()).filter(|p| p.extension().is_some_and(|x| x == "ron")).collect();
        paths.sort();
        let mut maps = Vec::new();
        for p in paths {
            maps.push(MapDef::load(&p)?);
        }
        Ok(Self::learn(&maps))
    }
}

// ---- difficulty ----------------------------------------------------------------------------------

/// How a level is set up; grows with the level number.
#[derive(Clone, Debug)]
pub struct Plan {
    pub side: u32,
    pub enemies: usize,
    pub enemy_colonies: usize,
    pub neutral_colonies: usize,
    pub boosters: usize,
    pub enemy_turrets: usize,
    /// starting units of each roster tier (light, medium, heavy)
    pub player_units: [u32; 3],
    pub enemy_units: [u32; 3],
    pub bot_profile: &'static str,
    /// enemy breeding speed (1 = normal)
    pub breed_speed: f32,
    /// creep counts relative to the original's levels of the tileset
    pub creep_scale: f32,
    pub bot_delay: f32,
    pub unit_cap: u32,
}

/// The set-up of procedural level `level` (1, 2, ...). Every level is at least as hard as the one
/// before: more enemy teams, colonies, turrets and units, smarter bots, then ever faster breeding.
pub fn plan(level: u32) -> Plan {
    let l = level.max(1);
    let lf = l as f32;
    Plan {
        side: match l {
            1..=2 => 64,
            3..=5 => 80,
            6..=10 => 96,
            11..=18 => 112,
            _ => 128,
        },
        enemies: match l {
            1..=2 => 1,
            3..=7 => 2,
            _ => 3,
        },
        enemy_colonies: (1 + (l as usize - 1) / 6).min(3),
        neutral_colonies: match l {
            1..=5 => 2,
            6..=10 => 3,
            _ => 4,
        },
        boosters: match l {
            1..=2 => 0,
            3..=11 => 1,
            _ => 2,
        },
        enemy_turrets: ((l as usize).saturating_sub(3) / 5).min(3),
        player_units: [4, 2, if l <= 3 { 1 } else { 0 }],
        enemy_units: [2 + l.min(36) / 3, l.min(36) / 4, l.min(36) / 8],
        bot_profile: match l {
            1..=3 => "easy",
            4..=9 => "medium",
            _ => "hard",
        },
        // keeps growing, ever more slowly: 1.0 up to level 10, 1.44 at 20, 1.84 at 50, 2.2 at 100
        breed_speed: if l <= 10 { 1.0 } else { 1.0 + 0.35 * (1.0 + (lf - 10.0) / 4.0).ln() },
        creep_scale: 0.75 + 0.05 * lf.min(25.0),
        bot_delay: (24.0 - lf).max(6.0),
        unit_cap: 100 + 5 * l.min(20),
    }
}

// ---- the generator -------------------------------------------------------------------------------

const FAMILIES: [(&str, &str); 5] = [("ant", "Ants"), ("beetle", "Beetles"), ("spider", "Spiders"), ("scorpion", "Scorpions"), ("wasp", "Wasps")];
const ENEMY_COLOURS: [&str; 3] = ["R", "G", "B"];

/// Seed of level `level` of a run.
pub fn level_seed(run_seed: u64, level: u32) -> u64 {
    let mut x = run_seed ^ (level as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15);
    // splitmix64 finaliser
    x = (x ^ (x >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    x = (x ^ (x >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    x ^ (x >> 31)
}

/// A level name in the tileset's flavour ("Murky Bog", "Sugary Toffee Fields").
fn level_name(tileset: &str, rng: &mut ChaCha8Rng) -> String {
    let (adj, noun): (&[&str], &[&str]) = match tileset {
        "desert" => (&["Dry", "Scorched", "Burning", "Dusty", "Bleached", "Red", "Thirsty", "Windswept"], &["Dunes", "Sands", "Mesa", "Wastes", "Flats", "Canyon", "Gulch", "Badlands"]),
        "swamp" => (&["Murky", "Rotten", "Misty", "Sunken", "Dank", "Foggy", "Slimy", "Drowned"], &["Marsh", "Bog", "Mire", "Fen", "Bayou", "Swamp", "Wetlands", "Hollow"]),
        "candy" => (&["Sticky", "Sugary", "Sour", "Gooey", "Frosted", "Crunchy", "Melting", "Fizzy"], &["Candyland", "Sweetshop", "Sugar Hills", "Toffee Fields", "Jelly Bay", "Fudge Flats", "Gumdrop Pass", "Caramel Coast"]),
        _ => (&["Green", "Windy", "Sunny", "Quiet", "Hidden", "Broken", "Thorny", "Wild"], &["Meadow", "Garden", "Clover", "Lawn", "Field", "Glade", "Pasture", "Hedgerow"]),
    };
    format!("{} {}", adj[rng.random_range(0..adj.len())], noun[rng.random_range(0..noun.len())])
}

/// Smooth value noise in [0, 1) over a `w` x `h` grid, features about `scale` cells across.
fn value_noise(w: usize, h: usize, scale: f32, rng: &mut ChaCha8Rng) -> Vec<f32> {
    let gw = (w as f32 / scale).ceil() as usize + 2;
    let gh = (h as f32 / scale).ceil() as usize + 2;
    let lattice: Vec<f32> = (0..gw * gh).map(|_| rng.random::<f32>()).collect();
    let smooth = |t: f32| t * t * (3.0 - 2.0 * t);
    let mut out = vec![0.0; w * h];
    for y in 0..h {
        for x in 0..w {
            let (fx, fy) = (x as f32 / scale, y as f32 / scale);
            let (ix, iy) = (fx as usize, fy as usize);
            let (tx, ty) = (smooth(fx - ix as f32), smooth(fy - iy as f32));
            let at = |i: usize, j: usize| lattice[j * gw + i];
            let a = at(ix, iy) + (at(ix + 1, iy) - at(ix, iy)) * tx;
            let b = at(ix, iy + 1) + (at(ix + 1, iy + 1) - at(ix, iy + 1)) * tx;
            out[y * w + x] = a + (b - a) * ty;
        }
    }
    out
}

/// Narrows the neighbours of every block on `stack` to the templates their sides allow; false on a
/// contradiction (a block with no template left).
fn propagate(tm: &TileModel, dom: &mut [Bits], bw: usize, bh: usize, stack: &mut Vec<usize>) -> bool {
    while let Some(i) = stack.pop() {
        let (x, y) = (i % bw, i / bw);
        let here = dom[i];
        let sides: [(bool, isize, &Vec<Bits>); 4] = [
            (x + 1 < bw, 1, &tm.right),
            (x > 0, -1, &tm.left),
            (y + 1 < bh, bw as isize, &tm.down),
            (y > 0, -(bw as isize), &tm.up),
        ];
        for (inside, step, rel) in sides {
            if !inside {
                continue;
            }
            let j = (i as isize + step) as usize;
            let mut allowed = NONE;
            for t in members(&here) {
                union(&mut allowed, &rel[t as usize]);
            }
            let narrowed = inter(&dom[j], &allowed);
            if narrowed != dom[j] {
                if count(&narrowed) == 0 {
                    return false;
                }
                dom[j] = narrowed;
                stack.push(j);
            }
        }
    }
    true
}

/// Fills a `bw` x `bh` grid of 2x2-cell blocks with templates: `keep` blocks get all-clear ones,
/// the rest follows `intent` (a terrain kind per block) as far as the neighbour rules allow.
fn lay_ground(tm: &TileModel, bw: usize, bh: usize, keep: &[bool], intent: &[usize], rng: &mut ChaCha8Rng) -> Option<Vec<u8>> {
    let clear: Bits = {
        let mut b = NONE;
        for t in members(&tm.all) {
            if tm.all_clear(t) {
                union(&mut b, &bit(t));
            }
        }
        b
    };
    let n = bw * bh;
    let mut dom: Vec<Bits> = (0..n).map(|i| if keep[i] { clear } else { tm.all }).collect();
    let mut stack: Vec<usize> = (0..n).collect();
    if !propagate(tm, &mut dom, bw, bh, &mut stack) {
        return None;
    }
    // how well a template suits the planned terrain of its block
    let fit = |t: u8, k: usize| {
        let m = (0..4).filter(|q| tm.kind(t, *q) == k).count() as f32 / 4.0;
        0.02 + m * m
    };
    loop {
        // the undecided block with the fewest templates left (random tie-break); the planned water,
        // rock and scrub first, before the plain ground round them rules their templates out
        let mut best: Option<(u32, usize)> = None;
        for (i, d) in dom.iter().enumerate() {
            let c = count(d);
            if c > 1 {
                let tier = if intent[i] == CLEAR { 1 << 20 } else { 0 };
                let key = tier + c * 64 + rng.random_range(0..64u32);
                if best.is_none_or(|(b, _)| key < b) {
                    best = Some((key, i));
                }
            }
        }
        let Some((_, i)) = best else { break };
        let options: Vec<(u8, f32)> = members(&dom[i]).map(|t| (t, tm.weight[t as usize].max(0.5) * fit(t, intent[i]))).collect();
        let total: f32 = options.iter().map(|o| o.1).sum();
        let mut r = rng.random::<f32>() * total;
        let mut pick = options[0].0;
        for (t, w) in &options {
            if r < *w {
                pick = *t;
                break;
            }
            r -= w;
        }
        dom[i] = bit(pick);
        stack.push(i);
        if !propagate(tm, &mut dom, bw, bh, &mut stack) {
            return None;
        }
    }
    Some(dom.iter().map(|d| members(d).next().unwrap_or(0)).collect())
}

/// The most used template that may sit next to itself in both directions and is all clear
/// (the plain ground every tileset has).
fn plain_ground(tm: &TileModel) -> Option<u8> {
    members(&tm.all).filter(|t| tm.all_clear(*t) && has(&tm.right[*t as usize], *t) && has(&tm.down[*t as usize], *t)).max_by(|a, b| tm.weight[*a as usize].total_cmp(&tm.weight[*b as usize]))
}

/// Whether every site can be walked up to (some cell round its footprint) from `from`, over cells
/// that are not water, not in `blocked` and not under a site.
fn connected(kinds: &[usize], blocked: &[bool], w: usize, h: usize, from: Vec2, sites: &[Site]) -> bool {
    let cell = |p: Vec2| (p.x.floor().clamp(0.0, w as f32 - 1.0) as usize, p.y.floor().clamp(0.0, h as f32 - 1.0) as usize);
    // footprints block (an army's muster, half 0, is only somewhere to reach)
    let under = |x: usize, y: usize| sites.iter().any(|s| s.half > 0.0 && (Vec2::new(x as f32 + 0.5, y as f32 + 0.5) - s.pos).abs().max_element() < s.half + 0.5);
    let free = |x: usize, y: usize| kinds[y * w + x] != WATER && !blocked[y * w + x] && !under(x, y);
    let (sx, sy) = cell(from);
    if !free(sx, sy) {
        return false;
    }
    let mut seen = vec![false; w * h];
    let mut queue = std::collections::VecDeque::from([(sx, sy)]);
    seen[sy * w + sx] = true;
    while let Some((x, y)) = queue.pop_front() {
        for (dx, dy) in [(1i32, 0i32), (-1, 0), (0, 1), (0, -1)] {
            let (nx, ny) = (x as i32 + dx, y as i32 + dy);
            if nx < 0 || ny < 0 || nx >= w as i32 || ny >= h as i32 {
                continue;
            }
            let (nx, ny) = (nx as usize, ny as usize);
            if !seen[ny * w + nx] && free(nx, ny) {
                seen[ny * w + nx] = true;
                queue.push_back((nx, ny));
            }
        }
    }
    sites.iter().all(|s| {
        // any cell of the ring round the footprint
        let r = s.half + 1.5;
        let (x0, y0) = cell(s.pos - Vec2::splat(r));
        let (x1, y1) = cell(s.pos + Vec2::splat(r));
        (y0..=y1).any(|y| (x0..=x1).any(|x| seen[y * w + x]))
    })
}

/// Something placed on the map that needs room: centre, half size of the footprint.
#[derive(Clone, Copy)]
struct Site {
    pos: Vec2,
    half: f32,
}

/// A free spot between `rmin` and `rmax` cells from `near` (cell-centred), at least `gap` cells
/// clear of every site, inside the map with `margin` cells to spare.
#[allow(clippy::too_many_arguments)]
fn find_spot(rng: &mut ChaCha8Rng, side: f32, sites: &[Site], near: Vec2, rmin: f32, rmax: f32, half: f32, gap: f32) -> Option<Vec2> {
    let margin = half + 2.0;
    for _ in 0..400 {
        let a = rng.random::<f32>() * std::f32::consts::TAU;
        let r = rmin + rng.random::<f32>() * (rmax - rmin).max(0.0);
        let p = near + Vec2::new(a.cos(), a.sin()) * r;
        let p = Vec2::new(p.x.floor() + 0.5, p.y.floor() + 0.5);
        if p.x < margin || p.y < margin || p.x > side - margin || p.y > side - margin {
            continue;
        }
        if sites.iter().all(|s| (p - s.pos).abs().max_element() >= s.half + half + gap) {
            return Some(p);
        }
    }
    None
}

/// How the ground of a level came about (tests and tuning).
#[derive(Clone, Debug, Default)]
pub struct GroundReport {
    /// fills that ran into a dead end (a block with no template left)
    pub dead_ends: u32,
    /// grounds rejected because water cut a colony or an army off
    pub cut_off: u32,
    /// plain ground everywhere after every attempt failed
    pub plain: bool,
}

/// Builds procedural level `level` of the run `run_seed`. The same seed and level always give the
/// same map.
pub fn generate(model: &GroundModel, defs: &Defs, level: u32, run_seed: u64) -> Result<MapDef, String> {
    generate_with_report(model, defs, level, run_seed).map(|(m, _)| m)
}

/// [`generate`], with an account of how the ground was laid.
pub fn generate_with_report(model: &GroundModel, defs: &Defs, level: u32, run_seed: u64) -> Result<(MapDef, GroundReport), String> {
    let mut report = GroundReport::default();
    let level = level.max(1);
    let seed = level_seed(run_seed, level);
    let mut rng = ChaCha8Rng::seed_from_u64(seed);
    let p = plan(level);
    let tilesets: Vec<&String> = model.tilesets.iter().filter(|(_, tm)| tm.levels > 0 && plain_ground(tm).is_some()).map(|(k, _)| k).collect();
    if tilesets.is_empty() {
        return Err("no original ground layouts to learn from".into());
    }
    let tileset = tilesets[rng.random_range(0..tilesets.len())].clone();
    let tm = &model.tilesets[&tileset];
    let side = p.side as f32;
    let centre = Vec2::splat(side * 0.5);
    let half_of = |id: &str| defs.colony(id).map(|c| defs.colonies[c as usize].half_extent).unwrap_or(3.0);

    // ---- teams and their families
    let mut families: Vec<usize> = (0..FAMILIES.len()).collect();
    for i in (1..families.len()).rev() {
        families.swap(i, rng.random_range(0..=i));
    }
    let teams_n = 1 + p.enemies;
    let mut teams = vec![TeamDef { id: 1, name: FAMILIES[families[0]].1.into(), color: "Y".into(), controller: Controller::Human, bot_profile: String::new(), ..Default::default() }];
    for e in 0..p.enemies {
        teams.push(TeamDef {
            id: e as u8 + 2,
            name: FAMILIES[families[e + 1]].1.into(),
            color: ENEMY_COLOURS[e].into(),
            controller: Controller::Bot,
            bot_profile: p.bot_profile.into(),
            breed_speed: p.breed_speed,
        });
    }

    // ---- homes: the teams spread round the map, the player's first
    let turn = rng.random::<f32>() * std::f32::consts::TAU;
    let ring = side * 0.5 - 3.0 - 6.0;
    let homes: Vec<Vec2> = (0..teams_n)
        .map(|i| {
            let a = turn + i as f32 / teams_n as f32 * std::f32::consts::TAU;
            // squares: push the ring out towards the corners
            let d = Vec2::new(a.cos(), a.sin());
            let d = d / d.abs().max_element();
            let at = centre + d * ring * 0.92;
            Vec2::new(at.x.floor() + 0.5, at.y.floor() + 0.5)
        })
        .collect();

    // ---- colonies and structures (`sites`: footprints; `taken`: those and the armies' musters)
    let mut sites: Vec<Site> = Vec::new();
    let mut taken: Vec<Site> = Vec::new();
    let mut colonies: Vec<ColonySpawn> = Vec::new();
    let colony_of = |f: usize| format!("colony_{}", FAMILIES[f].0);
    let mut muster: Vec<Vec2> = Vec::new();
    for (i, home) in homes.iter().enumerate() {
        let id = colony_of(families[i]);
        let half = half_of(&id);
        sites.push(Site { pos: *home, half });
        taken.push(Site { pos: *home, half });
        colonies.push(ColonySpawn { colony: id, team: i as u8 + 1, pos: *home, produce: None, defeated: false });
        // the starting army waits between the home colony and the middle
        let at = *home + (centre - *home).normalize_or_zero() * (half + 3.5);
        muster.push(at);
        taken.push(Site { pos: at, half: 2.5 });
    }
    for e in 0..p.enemies {
        let team = e as u8 + 2;
        let id = colony_of(families[e + 1]);
        let half = half_of(&id);
        let home = homes[e + 1];
        for _ in 1..p.enemy_colonies {
            let towards = home + (centre - home).normalize_or_zero() * 4.0;
            if let Some(pos) = find_spot(&mut rng, side, &taken, towards, 9.0, 15.0, half, 3.0) {
                sites.push(Site { pos, half });
                taken.push(Site { pos, half });
                colonies.push(ColonySpawn { colony: id.clone(), team, pos, produce: None, defeated: false });
            }
        }
        let turret = format!("turret_{}", FAMILIES[families[e + 1]].0);
        if defs.colony(&turret).is_some() {
            let th = half_of(&turret);
            for _ in 0..p.enemy_turrets {
                if let Some(pos) = find_spot(&mut rng, side, &taken, home + (centre - home).normalize_or_zero() * 7.0, 2.0, 7.0, th, 1.5) {
                    sites.push(Site { pos, half: th });
                    taken.push(Site { pos, half: th });
                    colonies.push(ColonySpawn { colony: turret.clone(), team, pos, produce: None, defeated: false });
                }
            }
        }
    }
    for _ in 0..p.neutral_colonies {
        let f = rng.random_range(0..FAMILIES.len());
        let id = colony_of(f);
        let half = half_of(&id);
        if let Some(pos) = find_spot(&mut rng, side, &taken, centre, 0.0, side * 0.32, half, 7.0) {
            sites.push(Site { pos, half });
            taken.push(Site { pos, half });
            colonies.push(ColonySpawn { colony: id, team: 0, pos, produce: None, defeated: false });
        }
    }
    for b in 0..p.boosters {
        let id = if b % 2 == 0 { "booster_production" } else { "booster_firepower" };
        if defs.colony(id).is_none() {
            continue;
        }
        let half = half_of(id);
        if let Some(pos) = find_spot(&mut rng, side, &taken, centre, 0.0, side * 0.25, half, 4.0) {
            sites.push(Site { pos, half });
            taken.push(Site { pos, half });
            colonies.push(ColonySpawn { colony: id.into(), team: 0, pos, produce: None, defeated: false });
        }
    }

    // ---- starting armies at their musters
    let mut units: Vec<UnitSpawn> = Vec::new();
    for (i, at) in muster.iter().enumerate() {
        let roster = defs.colony(&colony_of(families[i])).map(|c| defs.colonies[c as usize].produces.clone()).unwrap_or_default();
        let counts = if i == 0 { p.player_units } else { p.enemy_units };
        let at = *at;
        for (tier, n) in counts.iter().enumerate() {
            if *n > 0 && let Some(unit) = roster.get(tier) {
                units.push(UnitSpawn { unit: unit.clone(), team: i as u8 + 1, pos: at, count: *n, spread: 1.6 + (*n as f32).sqrt() * 0.5 });
            }
        }
    }

    // ---- ground: blocks of 2x2 cells, kept clear round everything placed
    let (w, h) = (p.side as usize, p.side as usize);
    let (bw, bh) = (w / 2, h / 2);
    let mut keep = vec![false; bw * bh];
    let mut keep_rect = |c: Vec2, r: f32| {
        let (x0, y0) = (((c.x - r) / 2.0).floor().max(0.0) as usize, ((c.y - r) / 2.0).floor().max(0.0) as usize);
        let (x1, y1) = ((((c.x + r) / 2.0).floor() as usize).min(bw - 1), (((c.y + r) / 2.0).floor() as usize).min(bh - 1));
        for y in y0..=y1 {
            for x in x0..=x1 {
                keep[y * bw + x] = true;
            }
        }
    };
    for s in &sites {
        keep_rect(s.pos, s.half + 2.0);
    }
    for m in &muster {
        keep_rect(*m, 3.5);
    }
    // every site and every army must be reachable from the player's army on foot
    let targets: Vec<Site> = sites.iter().copied().chain(muster.iter().map(|m| Site { pos: *m, half: 0.0 })).collect();
    let start = muster[0];

    let mut blocks: Option<Vec<u8>> = None;
    let mut kinds_grid: Vec<usize> = Vec::new();
    for attempt in 0..16 {
        // the terrain plan: water, rock and scrub where their noise is highest, as much of each as
        // the tileset's own levels have (none after many failed attempts)
        let amount = if attempt < 12 { 1.0 } else { 0.0 };
        let mut intent = vec![CLEAR; bw * bh];
        let mut best = vec![0.0f32; bw * bh];
        for k in [1usize, 2, 3] {
            // the plan's water grows by its shores when laid, rock and scrub shrink: aim off
            let aim = [1.0, 1.25, 1.6, 0.7][k];
            let share = (tm.share(k) * aim * amount).min(0.45);
            if share < 0.01 {
                continue;
            }
            let a = value_noise(bw, bh, 7.0, &mut rng);
            let b = value_noise(bw, bh, 3.0, &mut rng);
            let field: Vec<f32> = a.iter().zip(&b).map(|(a, b)| a * 0.75 + b * 0.25).collect();
            let mut sorted: Vec<f32> = field.iter().enumerate().filter(|(i, _)| !keep[*i]).map(|(_, v)| *v).collect();
            sorted.sort_by(|x, y| x.total_cmp(y));
            if sorted.is_empty() {
                continue;
            }
            let cut = sorted[((1.0 - share) * (sorted.len() - 1) as f32) as usize];
            for i in 0..bw * bh {
                let excess = field[i] - cut;
                if !keep[i] && excess > 0.0 && excess > best[i] {
                    best[i] = excess;
                    intent[i] = k;
                }
            }
        }
        let Some(laid) = lay_ground(tm, bw, bh, &keep, &intent, &mut rng) else {
            report.dead_ends += 1;
            continue;
        };
        let mut kinds = vec![CLEAR; w * h];
        for y in 0..h {
            for x in 0..w {
                let t = laid[(y / 2) * bw + x / 2];
                kinds[y * w + x] = tm.kind(t, (y % 2) * 2 + x % 2);
            }
        }
        if connected(&kinds, &vec![false; w * h], w, h, start, &targets) {
            blocks = Some(laid);
            kinds_grid = kinds;
            break;
        }
        report.cut_off += 1;
    }
    let blocks = match blocks {
        Some(b) => b,
        None => {
            // plain ground everywhere: always valid
            report.plain = true;
            let t = plain_ground(tm).ok_or("no plain ground template")?;
            kinds_grid = vec![CLEAR; w * h];
            vec![t; bw * bh]
        }
    };
    let mut tiles = String::with_capacity(w * h * 3 + h);
    let mut cells = String::with_capacity(w * h + h);
    for y in 0..h {
        for x in 0..w {
            let t = blocks[(y / 2) * bw + x / 2];
            tiles.push_str(&format!("{:02x}{:x}", t, (y % 2) * 2 + x % 2));
            cells.push(KINDS[kinds_grid[y * w + x]] as char);
        }
        tiles.push('\n');
        cells.push('\n');
    }

    // ---- props: the tileset's own, as thick as in its levels, out of everyone's way
    let mut obstacles = Vec::new();
    let clear_cells = kinds_grid.iter().filter(|k| **k != WATER).count() as f32;
    let total_props: u32 = tm.props.values().map(|s| s.count).sum();
    let n_cells_levels: u64 = tm.cells.iter().sum::<u64>().max(1);
    let density = total_props as f32 / n_cells_levels as f32;
    let wanted = (density * clear_cells) as usize;
    let mut blocked = vec![false; w * h];
    let in_keep = |x: usize, y: usize| keep[(y / 2).min(bh - 1) * bw + (x / 2).min(bw - 1)];
    let kinds_list: Vec<(&String, &PropStat)> = tm.props.iter().collect();
    for _ in 0..wanted * 4 {
        if obstacles.len() >= wanted || kinds_list.is_empty() {
            break;
        }
        let (x, y) = (rng.random_range(1..w - 1), rng.random_range(1..h - 1));
        if in_keep(x, y) || (0..9).any(|n| {
            let (nx, ny) = (x + n % 3 - 1, y + n / 3 - 1);
            kinds_grid[ny * w + nx] == WATER || blocked[ny * w + nx]
        }) {
            continue;
        }
        let mut r = rng.random_range(0..total_props.max(1));
        let (kind, stat) = kinds_list.iter().find(|(_, s)| {
            if r < s.count {
                true
            } else {
                r -= s.count;
                false
            }
        }).copied().unwrap_or(kinds_list[0]);
        let n = stat.count.max(1) as f32;
        let blocking = stat.blocking * 2 >= stat.count;
        blocked[y * w + x] = blocking;
        obstacles.push(Obstacle {
            kind: kind.clone(),
            pos: Vec2::new(x as f32 + 0.5, y as f32 + 0.5),
            radius: stat.radius / n,
            yaw: rng.random::<f32>() * std::f32::consts::TAU,
            scale: stat.scale / n * (0.85 + rng.random::<f32>() * 0.3),
            blocking,
        });
    }
    if !connected(&kinds_grid, &blocked, w, h, start, &targets) {
        for o in obstacles.iter_mut() {
            o.blocking = false;
        }
    }

    // ---- creeps: the pools the tileset's levels have, more of them as the levels go on
    let mut creeps = Vec::new();
    let area_scale = ((w * h) as f64 / tm.area.max(1.0)).clamp(0.5, 2.0) as f32;
    let pool = |units: &str, stat: &CreepStat| {
        let mut counts = stat.counts.clone();
        counts.sort();
        let typical = counts[counts.len() / 2] as f32;
        let count = (typical * p.creep_scale * area_scale).round().max(1.0) as u32;
        CreepPool { units: units.split(',').map(String::from).collect(), count, interval: stat.interval, first: stat.first }
    };
    // each pool as often as the tileset's levels have it; at least the most common one
    for (units, stat) in &tm.creeps {
        if rng.random::<f32>() < stat.levels as f32 / tm.levels.max(1) as f32 {
            creeps.push(pool(units, stat));
        }
    }
    if creeps.is_empty() && let Some((units, stat)) = tm.creeps.iter().max_by_key(|(_, s)| s.levels) {
        creeps.push(pool(units, stat));
    }

    let name = level_name(&tileset, &mut rng);
    let map = MapDef {
        name,
        width: p.side,
        height: p.side,
        tileset,
        seed,
        obstacles,
        colonies,
        units,
        teams,
        rules: MapRules { unit_cap: Some(p.unit_cap), creeps, bot_delay: p.bot_delay, ..Default::default() },
        description: format!("Procedural level {level}"),
        cells: Some(cells),
        camera: Some(homes[0]),
        category: "procedural".into(),
        number: Some(level),
        author: "procedural".into(),
        tiles: Some(tiles),
        run_seed: Some(run_seed),
        ..Default::default()
    };
    Ok((map, report))
}
