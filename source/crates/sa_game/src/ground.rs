//! The 3-D ground. Each level's layout (where the open ground, the water, the rock and the
//! vegetation are) comes from the original level; the ground itself is modelled in 3-D:
//!
//! * a height field: lakes sink into the ground, rock and vegetation rise a little, the edges of
//!   the map continue into an apron that fades into the dark;
//! * a terrain shader (assets/shaders/terrain.wesl) blending four tileable PBR layers per tileset
//!   (tools/make_terrain_textures.py) with height-based transitions;
//! * water surfaces with moving ripples at a common water level;
//! * 3-D props scattered over the layers: bushes / boulders / crystals / jelly drops on the
//!   vegetation layer, loose stones on the rock layer, reeds along the shores.
//!
//! With the player's copy of the original game the layer shapes are classified from the original
//! tile pictures (the shores and patches follow the original's outlines pixel for pixel); without
//! it they come from the per-cell terrain of the level file, softened with noise.

use std::collections::HashMap;

use bevy::asset::RenderAssetUsages;
use bevy::image::{CompressedImageFormats, ImageAddressMode, ImageFilterMode, ImageSampler, ImageSamplerDescriptor, ImageType};
use bevy::light::NotShadowCaster;
use bevy::math::Affine2;
use bevy::mesh::{Indices, PrimitiveTopology, VertexAttributeValues};
use bevy::pbr::{ExtendedMaterial, MaterialExtension};
use bevy::prelude::*;
use bevy::render::render_resource::{AsBindGroup, Extent3d, ShaderType, TextureDimension, TextureFormat, TextureViewDescriptor, TextureViewDimension};
use bevy::shader::ShaderRef;
use bevy::state::state_scoped::DespawnOnExit;
use sa_sim::TerrainKind;

use crate::AppState;
use crate::original::{Original, OriginalGame, Rgba};
use crate::sim_plugin::GameSim;

pub type TerrainMaterial = ExtendedMaterial<StandardMaterial, TerrainExt>;

/// Weight-map samples per cell.
const R: usize = 4;
/// Height-grid vertices per cell.
const V: usize = 2;
/// Cells of ground modelled beyond each map edge.
const APRON: i32 = 8;
/// Height of every water surface (lake beds lie below it).
pub const WATER_LEVEL: f32 = -0.13;
/// Depth of a fully submerged lake bed.
const LAKE_DEPTH: f32 = 0.42;

pub struct GroundPlugin;

impl Plugin for GroundPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins(MaterialPlugin::<TerrainMaterial>::default())
            .add_systems(OnEnter(AppState::InGame), spawn_ground)
            .add_systems(Update, animate_water.run_if(in_state(AppState::InGame)));
    }
}

/// Uniforms of the terrain shader (see terrain.wesl).
#[derive(Clone, Copy, Debug, ShaderType)]
pub struct TerrainParams {
    pub map: Vec4,
    pub roughness: Vec4,
    pub normal_strength: Vec4,
    pub layer_scale: Vec4,
    pub water: Vec4,
}

#[derive(Asset, AsBindGroup, TypePath, Debug, Clone)]
pub struct TerrainExt {
    #[uniform(100)]
    pub params: TerrainParams,
    #[texture(101)]
    #[sampler(102)]
    pub splat: Handle<Image>,
    #[texture(103, dimension = "2d_array")]
    #[sampler(104)]
    pub albedo: Handle<Image>,
    #[texture(105, dimension = "2d_array")]
    #[sampler(106)]
    pub normal: Handle<Image>,
}

impl MaterialExtension for TerrainExt {
    fn fragment_shader() -> ShaderRef {
        "shaders/terrain.wesl".into()
    }
}

/// Radar colours of the level, one RGBA pixel per cell (the layers in the tileset's colours).
#[derive(Resource, Clone)]
pub struct RadarBase {
    pub rgba: Vec<u8>,
}

/// Radar colours of the four layers per tileset (ground, water, rock, vegetation), after the
/// colours of the original tiles.
pub(crate) fn radar_palette(tileset: &str) -> [[f32; 3]; 4] {
    let c = |h: u32| [((h >> 16) & 255) as f32, ((h >> 8) & 255) as f32, (h & 255) as f32];
    match tileset {
        "desert" => [c(0xb77c48), c(0x4a3a30), c(0x847d76), c(0x5a4a40)],
        "swamp" => [c(0x6d6b52), c(0x2f4a36), c(0x3a4a26), c(0x3c5468)],
        "candy" => [c(0xb4a392), c(0x816c7d), c(0x7e6457), c(0x8a2a24)],
        _ => [c(0xa48669), c(0x4a5a7a), c(0x7c7464), c(0x36512d)],
    }
}

fn radar_base(layers: &LayerMap, w: i32, h: i32, tileset: &str) -> RadarBase {
    let pal = radar_palette(tileset);
    let mut rgba = Vec::with_capacity((w * h * 4) as usize);
    for y in 0..h {
        for x in 0..w {
            let wt = layers.sample(x as f32 + 0.5, y as f32 + 0.5);
            let mut col = [0.0f32; 3];
            for (l, p) in pal.iter().enumerate() {
                for c in 0..3 {
                    col[c] += p[c] * wt[l];
                }
            }
            rgba.extend_from_slice(&[col[0] as u8, col[1] as u8, col[2] as u8, 255]);
        }
    }
    RadarBase { rgba }
}

/// Ground height for placing units, colonies and props (bilinear over the height grid).
#[derive(Resource, Clone)]
pub struct GroundHeight {
    origin: f32,
    cols: usize,
    rows: usize,
    heights: Vec<f32>,
}

impl GroundHeight {
    pub fn at(&self, x: f32, z: f32) -> f32 {
        let gx = ((x - self.origin) * V as f32).clamp(0.0, (self.cols - 1) as f32);
        let gz = ((z - self.origin) * V as f32).clamp(0.0, (self.rows - 1) as f32);
        let (x0, z0) = (gx.floor() as usize, gz.floor() as usize);
        let (x1, z1) = ((x0 + 1).min(self.cols - 1), (z0 + 1).min(self.rows - 1));
        let (fx, fz) = (gx - x0 as f32, gz - z0 as f32);
        let h = |x: usize, z: usize| self.heights[z * self.cols + x];
        let a = h(x0, z0) + (h(x1, z0) - h(x0, z0)) * fx;
        let b = h(x0, z1) + (h(x1, z1) - h(x0, z1)) * fx;
        a + (b - a) * fz
    }

    /// Height for something standing at (x, z): never below the water surface.
    pub fn stand(&self, x: f32, z: f32) -> f32 {
        self.at(x, z).max(WATER_LEVEL)
    }
}

/// Per-tileset look of the 3-D ground.
struct Look {
    water: Color,
    water_alpha: f32,
    roughness: Vec4,
    normal_strength: Vec4,
    /// texture repeats per cell for each layer (relative to 1/3)
    layer_scale: Vec4,
    veg: VegKind,
    stones: StoneKind,
    reeds: bool,
}

#[derive(Clone, Copy, PartialEq)]
enum VegKind {
    Bush,
    Boulder,
    Crystal,
    Jelly,
}

#[derive(Clone, Copy, PartialEq)]
enum StoneKind {
    Pebble,
    Gravel,
    MossTuft,
    Crumb,
}

fn look(tileset: &str) -> Look {
    match tileset {
        "desert" => Look {
            water: Color::srgb(0.33, 0.25, 0.18),
            water_alpha: 0.9,
            roughness: Vec4::new(0.9, 0.35, 0.85, 0.8),
            normal_strength: Vec4::new(0.8, 0.4, 1.2, 1.4),
            layer_scale: Vec4::new(1.0, 1.0, 1.4, 0.8),
            veg: VegKind::Boulder,
            stones: StoneKind::Gravel,
            reeds: false,
        },
        "swamp" => Look {
            water: Color::srgb(0.16, 0.27, 0.18),
            water_alpha: 0.86,
            roughness: Vec4::new(0.85, 0.4, 0.9, 0.35),
            normal_strength: Vec4::new(1.3, 0.5, 1.0, 1.2),
            layer_scale: Vec4::new(0.7, 1.0, 1.0, 0.9),
            veg: VegKind::Crystal,
            stones: StoneKind::MossTuft,
            reeds: true,
        },
        "candy" => Look {
            water: Color::srgb(0.47, 0.30, 0.45),
            water_alpha: 0.9,
            roughness: Vec4::new(0.7, 0.2, 0.75, 0.2),
            normal_strength: Vec4::new(0.9, 0.3, 1.2, 1.0),
            layer_scale: Vec4::new(1.0, 1.0, 1.1, 0.9),
            veg: VegKind::Jelly,
            stones: StoneKind::Crumb,
            reeds: false,
        },
        _ => Look {
            water: Color::srgb(0.25, 0.33, 0.46),
            water_alpha: 0.7,
            roughness: Vec4::new(0.92, 0.5, 0.8, 0.9),
            normal_strength: Vec4::new(0.9, 0.4, 1.3, 1.0),
            layer_scale: Vec4::new(1.0, 1.0, 1.2, 1.0),
            veg: VegKind::Bush,
            stones: StoneKind::Pebble,
            reeds: true,
        },
    }
}

// ---- noise ----------------------------------------------------------------------------------

fn hash(x: i32, y: i32, seed: u32) -> f32 {
    let mut h = (x as u32).wrapping_mul(374_761_393) ^ (y as u32).wrapping_mul(668_265_263) ^ seed.wrapping_mul(2_246_822_519);
    h = (h ^ (h >> 13)).wrapping_mul(1_274_126_177);
    ((h ^ (h >> 16)) & 0xffff) as f32 / 65535.0
}

/// Smooth value noise in 0..1 with features about `scale` cells wide.
fn noise(x: f32, y: f32, scale: f32, seed: u32) -> f32 {
    let (fx, fy) = (x / scale, y / scale);
    let (ix, iy) = (fx.floor() as i32, fy.floor() as i32);
    let (tx, ty) = (fx - ix as f32, fy - iy as f32);
    let s = |t: f32| t * t * (3.0 - 2.0 * t);
    let (sx, sy) = (s(tx), s(ty));
    let a = hash(ix, iy, seed) + (hash(ix + 1, iy, seed) - hash(ix, iy, seed)) * sx;
    let b = hash(ix, iy + 1, seed) + (hash(ix + 1, iy + 1, seed) - hash(ix, iy + 1, seed)) * sx;
    a + (b - a) * sy
}

// ---- layer weights --------------------------------------------------------------------------

/// Layer weights (ground, water bed, rock, vegetation) at R x R samples per cell.
struct LayerMap {
    w: usize,
    h: usize,
    wts: Vec<[f32; 4]>,
}

impl LayerMap {
    /// Bilinear sample at a map position in cells (clamped to the map).
    fn sample(&self, x: f32, y: f32) -> [f32; 4] {
        let gx = (x * R as f32 - 0.5).clamp(0.0, (self.w - 1) as f32);
        let gy = (y * R as f32 - 0.5).clamp(0.0, (self.h - 1) as f32);
        let (x0, y0) = (gx.floor() as usize, gy.floor() as usize);
        let (x1, y1) = ((x0 + 1).min(self.w - 1), (y0 + 1).min(self.h - 1));
        let (fx, fy) = (gx - x0 as f32, gy - y0 as f32);
        let mut out = [0.0; 4];
        for (c, o) in out.iter_mut().enumerate() {
            let p = |x: usize, y: usize| self.wts[y * self.w + x][c];
            let a = p(x0, y0) + (p(x1, y0) - p(x0, y0)) * fx;
            let b = p(x0, y1) + (p(x1, y1) - p(x0, y1)) * fx;
            *o = a + (b - a) * fy;
        }
        out
    }

    /// Box blur of every channel (`radius` samples), weights renormalised.
    fn blur(&mut self, radius: usize) {
        if radius == 0 {
            return;
        }
        let (w, h) = (self.w, self.h);
        let mut tmp = vec![[0.0f32; 4]; w * h];
        for y in 0..h {
            for x in 0..w {
                let mut acc = [0.0f32; 4];
                let mut n = 0.0;
                for dx in -(radius as i32)..=radius as i32 {
                    let sx = (x as i32 + dx).clamp(0, w as i32 - 1) as usize;
                    let v = self.wts[y * w + sx];
                    for c in 0..4 {
                        acc[c] += v[c];
                    }
                    n += 1.0;
                }
                tmp[y * w + x] = acc.map(|a| a / n);
            }
        }
        for y in 0..h {
            for x in 0..w {
                let mut acc = [0.0f32; 4];
                for dy in -(radius as i32)..=radius as i32 {
                    let sy = (y as i32 + dy).clamp(0, h as i32 - 1) as usize;
                    let v = tmp[sy * w + x];
                    for c in 0..4 {
                        acc[c] += v[c];
                    }
                }
                let s: f32 = acc.iter().sum::<f32>().max(1e-6);
                self.wts[y * w + x] = acc.map(|a| a / s);
            }
        }
    }
}

/// Template id -> picture name for each tileset (`assets/data/tilesets.ron`).
fn load_tilesets() -> HashMap<String, HashMap<u32, String>> {
    let path = std::path::PathBuf::from(crate::asset_root()).join("data/tilesets.ron");
    match std::fs::read_to_string(&path) {
        Ok(t) => ron::from_str(sa_sim::data::strip_bom(&t)).unwrap_or_else(|e| {
            warn!("{}: {e}", path.display());
            HashMap::new()
        }),
        Err(_) => HashMap::new(),
    }
}

/// The two layers a family of original tiles mixes: A = ground + water, B = ground,
/// C = ground + rock, D = rock + vegetation.
fn family_layers(family: char) -> (usize, usize) {
    match family {
        'A' => (0, 1),
        'C' => (0, 2),
        'D' => (2, 3),
        _ => (0, 0),
    }
}

type Rgb = [f32; 3];

fn dist2(a: Rgb, b: Rgb) -> f32 {
    (a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)
}

fn mean(px: &[Rgb]) -> Rgb {
    let n = px.len().max(1) as f32;
    let mut s = [0.0f32; 3];
    for p in px {
        for c in 0..3 {
            s[c] += p[c];
        }
    }
    s.map(|v| v / n)
}

/// Two-means clustering started from a known colour `a` and the far half of the pixels.
fn two_means(px: &[Rgb], a: Rgb) -> (Rgb, Rgb) {
    if px.is_empty() {
        return (a, a);
    }
    let mut d: Vec<f32> = px.iter().map(|p| dist2(*p, a)).collect();
    let mut sorted = d.clone();
    sorted.sort_by(|x, y| x.total_cmp(y));
    let median = sorted[sorted.len() / 2];
    let far: Vec<Rgb> = px.iter().zip(&d).filter(|(_, dd)| **dd >= median).map(|(p, _)| *p).collect();
    let (mut ca, mut cb) = (a, mean(&far));
    for _ in 0..12 {
        let (mut sa, mut sb) = (Vec::new(), Vec::new());
        for (i, p) in px.iter().enumerate() {
            d[i] = dist2(*p, ca);
            if d[i] <= dist2(*p, cb) {
                sa.push(*p);
            } else {
                sb.push(*p);
            }
        }
        if sa.is_empty() || sb.is_empty() {
            break;
        }
        ca = mean(&sa);
        cb = mean(&sb);
    }
    (ca, cb)
}

/// Layer weights classified from the original tile pictures.
fn layers_from_original(sim: &GameSim, orig: &OriginalGame) -> Option<LayerMap> {
    let tiles = sim.world.map.tiles.as_ref()?;
    let sets = load_tilesets();
    let set = sets.get(&sim.world.map.tileset)?;
    // decode the tileset's pictures once
    let mut pics: HashMap<u32, (char, Rgba)> = HashMap::new();
    for (tid, name) in set {
        if let Some(p) = orig.picture(name) {
            pics.insert(*tid, (name.chars().nth(7).unwrap_or('B'), p));
        }
    }
    if pics.is_empty() {
        return None;
    }
    // reference colours: every family's two clusters (sub-sampled pixels)
    let mut fam_px: HashMap<char, Vec<Rgb>> = HashMap::new();
    for (fam, p) in pics.values() {
        let v = fam_px.entry(*fam).or_default();
        for i in (0..(p.w * p.h) as usize).step_by(3) {
            v.push([p.px[i * 4] as f32, p.px[i * 4 + 1] as f32, p.px[i * 4 + 2] as f32]);
        }
    }
    let ground = mean(fam_px.get(&'B').map(|v| v.as_slice()).unwrap_or(&[]));
    let mut refs: HashMap<char, (Rgb, Rgb)> = HashMap::new();
    refs.insert('B', (ground, ground));
    refs.insert('A', two_means(fam_px.get(&'A').map(|v| v.as_slice()).unwrap_or(&[]), ground));
    let c = two_means(fam_px.get(&'C').map(|v| v.as_slice()).unwrap_or(&[]), ground);
    refs.insert('C', c);
    refs.insert('D', two_means(fam_px.get(&'D').map(|v| v.as_slice()).unwrap_or(&[]), c.1));

    let (w, h) = (sim.world.grid.w as usize, sim.world.grid.h as usize);
    let (sw, sh) = (w * R, h * R);
    let mut votes = vec![[0u32; 4]; sw * sh];
    let px_per_sample = 24 / R;
    for (y, row) in tiles.split('\n').map(str::trim).filter(|r| !r.is_empty()).enumerate().take(h) {
        let cells = row.as_bytes();
        for x in 0..(cells.len() / 3).min(w) {
            let hex = |s: &[u8]| std::str::from_utf8(s).ok().and_then(|s| u32::from_str_radix(s, 16).ok());
            let (Some(tid), Some(q)) = (hex(&cells[x * 3..x * 3 + 2]), hex(&cells[x * 3 + 2..x * 3 + 3])) else { continue };
            let Some((fam, pic)) = pics.get(&tid) else { continue };
            let (la, lb) = family_layers(*fam);
            let (ra, rb) = refs.get(fam).copied().unwrap_or((ground, ground));
            let (ox, oy) = ((q % 2) as usize * 24, (q / 2 % 2) as usize * 24);
            for py in 0..24 {
                for px in 0..24 {
                    let i = ((oy + py) * pic.w as usize + ox + px) * 4;
                    let c = [pic.px[i] as f32, pic.px[i + 1] as f32, pic.px[i + 2] as f32];
                    let layer = if la == lb || dist2(c, ra) <= dist2(c, rb) { la } else { lb };
                    let s = (y * R + py / px_per_sample) * sw + x * R + px / px_per_sample;
                    votes[s][layer] += 1;
                }
            }
        }
    }
    let wts = votes
        .into_iter()
        .map(|v| {
            let n = (v[0] + v[1] + v[2] + v[3]).max(1) as f32;
            if v.iter().sum::<u32>() == 0 { [1.0, 0.0, 0.0, 0.0] } else { v.map(|c| c as f32 / n) }
        })
        .collect();
    let mut map = LayerMap { w: sw, h: sh, wts };
    map.blur(1);
    Some(map)
}

/// Layer weights from the level's per-cell terrain, with noisy, softened outlines.
fn layers_from_cells(sim: &GameSim) -> LayerMap {
    let grid = &sim.world.grid;
    let (w, h) = (grid.w as usize, grid.h as usize);
    let (sw, sh) = (w * R, h * R);
    let mut wts = vec![[0.0f32; 4]; sw * sh];
    for sy in 0..sh {
        for sx in 0..sw {
            let (x, y) = ((sx / R) as i32, (sy / R) as i32);
            let layer = match grid.terrain_kind(IVec2::new(x, y)) {
                TerrainKind::Clear => 0,
                TerrainKind::Water => 1,
                TerrainKind::Rock => 2,
                TerrainKind::Vegetation => 3,
            };
            wts[sy * sw + sx][layer] = 1.0;
        }
    }
    let mut map = LayerMap { w: sw, h: sh, wts };
    map.blur(R);
    // wobble the outlines: push each sample's weights by noise, then sharpen
    for sy in 0..sh {
        for sx in 0..sw {
            let (fx, fy) = (sx as f32 / R as f32, sy as f32 / R as f32);
            let v = &mut map.wts[sy * sw + sx];
            for (c, val) in v.iter_mut().enumerate() {
                let n = noise(fx, fy, 1.7, 11 + c as u32) - 0.5;
                *val = ((*val + n * 0.35 - 0.5) * 2.5 + 0.5).clamp(0.0, 1.0);
            }
            let s: f32 = v.iter().sum::<f32>().max(1e-6);
            *v = v.map(|a| a / s);
        }
    }
    map.blur(1);
    map
}

// ---- height field and meshes ----------------------------------------------------------------

/// Heights of the ground vertices (V per cell, APRON cells beyond each edge).
fn build_heights(layers: &LayerMap, w: i32, h: i32, seed: u32) -> GroundHeight {
    let cols = ((w + 2 * APRON) as usize) * V + 1;
    let rows = ((h + 2 * APRON) as usize) * V + 1;
    let origin = -(APRON as f32);
    let mut heights = vec![0.0f32; cols * rows];
    for r in 0..rows {
        for c in 0..cols {
            let (x, z) = (origin + c as f32 / V as f32, origin + r as f32 / V as f32);
            let [_, bed, rock, veg] = layers.sample(x.clamp(0.0, w as f32), z.clamp(0.0, h as f32));
            let n1 = noise(x, z, 0.9, seed);
            let n2 = noise(x, z, 2.3, seed + 1);
            let n3 = noise(x, z, 6.0, seed + 2);
            let mut y = -LAKE_DEPTH * bed.powf(0.8);
            y += rock * (0.03 + 0.06 * n1);
            y += veg * (0.04 + 0.05 * n2);
            y += (n3 - 0.5) * 0.05 * (1.0 - bed);
            heights[r * cols + c] = y;
        }
    }
    // soften the shores (two box passes)
    for _ in 0..2 {
        let src = heights.clone();
        for r in 0..rows {
            for c in 0..cols {
                let mut acc = 0.0;
                let mut n = 0.0;
                for dr in -1i32..=1 {
                    for dc in -1i32..=1 {
                        let rr = (r as i32 + dr).clamp(0, rows as i32 - 1) as usize;
                        let cc = (c as i32 + dc).clamp(0, cols as i32 - 1) as usize;
                        acc += src[rr * cols + cc];
                        n += 1.0;
                    }
                }
                heights[r * cols + c] = acc / n;
            }
        }
    }
    GroundHeight { origin, cols, rows, heights }
}

fn ground_mesh(gh: &GroundHeight, w: i32, h: i32) -> Mesh {
    let (cols, rows) = (gh.cols, gh.rows);
    let step = 1.0 / V as f32;
    let mut positions = Vec::with_capacity(cols * rows);
    let mut normals = Vec::with_capacity(cols * rows);
    let mut uvs = Vec::with_capacity(cols * rows);
    for r in 0..rows {
        for c in 0..cols {
            let (x, z) = (gh.origin + c as f32 * step, gh.origin + r as f32 * step);
            let y = gh.heights[r * cols + c];
            positions.push([x, y, z]);
            let hl = gh.heights[r * cols + c.saturating_sub(1)];
            let hr = gh.heights[r * cols + (c + 1).min(cols - 1)];
            let hd = gh.heights[r.saturating_sub(1) * cols + c];
            let hu = gh.heights[(r + 1).min(rows - 1) * cols + c];
            let n = Vec3::new(hl - hr, 2.0 * step, hd - hu).normalize();
            normals.push(n.to_array());
            uvs.push([x / w as f32, z / h as f32]);
        }
    }
    let mut indices = Vec::with_capacity((cols - 1) * (rows - 1) * 6);
    for r in 0..rows - 1 {
        for c in 0..cols - 1 {
            let a = (r * cols + c) as u32;
            let row = cols as u32;
            indices.extend_from_slice(&[a, a + row + 1, a + 1, a, a + row, a + row + 1]);
        }
    }
    let mut mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default());
    mesh.insert_attribute(Mesh::ATTRIBUTE_POSITION, positions);
    mesh.insert_attribute(Mesh::ATTRIBUTE_NORMAL, normals);
    mesh.insert_attribute(Mesh::ATTRIBUTE_UV_0, uvs);
    mesh.insert_indices(Indices::U32(indices));
    mesh
}

// ---- textures -------------------------------------------------------------------------------

fn repeat_sampler() -> ImageSampler {
    ImageSampler::Descriptor(ImageSamplerDescriptor {
        address_mode_u: ImageAddressMode::Repeat,
        address_mode_v: ImageAddressMode::Repeat,
        mag_filter: ImageFilterMode::Linear,
        min_filter: ImageFilterMode::Linear,
        mipmap_filter: ImageFilterMode::Linear,
        anisotropy_clamp: 16,
        ..default()
    })
}

fn clamp_linear_sampler() -> ImageSampler {
    ImageSampler::Descriptor(ImageSamplerDescriptor {
        address_mode_u: ImageAddressMode::ClampToEdge,
        address_mode_v: ImageAddressMode::ClampToEdge,
        mag_filter: ImageFilterMode::Linear,
        min_filter: ImageFilterMode::Linear,
        ..default()
    })
}

/// RGBA8 pixels of a PNG in assets/textures/terrain.
fn load_png(name: &str) -> Option<(u32, u32, Vec<u8>)> {
    let path = std::path::PathBuf::from(crate::asset_root()).join("textures/terrain").join(name);
    let bytes = std::fs::read(&path).map_err(|e| warn!("{}: {e}", path.display())).ok()?;
    let img = Image::from_buffer(&bytes, ImageType::Extension("png"), CompressedImageFormats::NONE, false, ImageSampler::Default, RenderAssetUsages::default())
        .map_err(|e| warn!("{}: {e}", path.display()))
        .ok()?;
    let img = img.convert(TextureFormat::Rgba8Unorm).unwrap_or(img);
    let (w, h) = (img.width(), img.height());
    Some((w, h, img.data?))
}

/// Box-filtered mip chain of an RGBA8 picture (base level first).
fn mip_chain(w: u32, h: u32, base: Vec<u8>) -> Vec<Vec<u8>> {
    let mut levels = vec![base];
    let (mut w, mut h) = (w, h);
    while w > 1 || h > 1 {
        let (nw, nh) = ((w / 2).max(1), (h / 2).max(1));
        let prev = levels.last().unwrap();
        let mut next = vec![0u8; (nw * nh * 4) as usize];
        for y in 0..nh {
            for x in 0..nw {
                for c in 0..4 {
                    let mut sum = 0u32;
                    for (dx, dy) in [(0, 0), (1, 0), (0, 1), (1, 1)] {
                        sum += prev[((((y * 2 + dy).min(h - 1)) * w + (x * 2 + dx).min(w - 1)) * 4 + c) as usize] as u32;
                    }
                    next[((y * nw + x) * 4 + c) as usize] = (sum / 4) as u8;
                }
            }
        }
        levels.push(next);
        w = nw;
        h = nh;
    }
    levels
}

/// A 2-D array texture (one layer per picture, all the same size) with mip maps.
fn texture_array(layers: Vec<(u32, u32, Vec<u8>)>, srgb: bool) -> Option<Image> {
    let (w, h) = (layers.first()?.0, layers.first()?.1);
    if layers.iter().any(|l| l.0 != w || l.1 != h) {
        warn!("terrain textures must all have the same size");
        return None;
    }
    let mut data = Vec::new();
    let mut mips = 1;
    for (_, _, px) in &layers {
        let chain = mip_chain(w, h, px.clone());
        mips = chain.len() as u32;
        for level in chain {
            data.extend_from_slice(&level);
        }
    }
    let mut img = Image::new_uninit(
        Extent3d { width: w, height: h, depth_or_array_layers: layers.len() as u32 },
        TextureDimension::D2,
        if srgb { TextureFormat::Rgba8UnormSrgb } else { TextureFormat::Rgba8Unorm },
        RenderAssetUsages::RENDER_WORLD,
    );
    img.texture_descriptor.mip_level_count = mips;
    img.data = Some(data);
    img.texture_view_descriptor = Some(TextureViewDescriptor { dimension: Some(TextureViewDimension::D2Array), ..default() });
    img.sampler = repeat_sampler();
    Some(img)
}

// ---- props ----------------------------------------------------------------------------------

/// Positions, normals, colours and indices of a mesh built from transformed pieces.
#[derive(Default)]
struct PropBuilder {
    pos: Vec<[f32; 3]>,
    nrm: Vec<[f32; 3]>,
    col: Vec<[f32; 4]>,
    idx: Vec<u32>,
}

impl PropBuilder {
    /// Add a mesh transformed by `tf`, coloured per vertex by `color(local position)`.
    fn add(&mut self, mesh: &Mesh, tf: Transform, displace: impl Fn(Vec3) -> f32, color: impl Fn(Vec3, Vec3) -> [f32; 4]) {
        let base = self.pos.len() as u32;
        let (Some(VertexAttributeValues::Float32x3(p)), Some(VertexAttributeValues::Float32x3(n))) = (mesh.attribute(Mesh::ATTRIBUTE_POSITION), mesh.attribute(Mesh::ATTRIBUTE_NORMAL)) else {
            return;
        };
        for (p, n) in p.iter().zip(n) {
            let lp = Vec3::from_array(*p);
            let ln = Vec3::from_array(*n);
            let lp = lp + ln * displace(lp);
            let wp = tf.transform_point(lp);
            let wn = (tf.rotation * (ln / tf.scale)).normalize_or_zero();
            self.pos.push(wp.to_array());
            self.nrm.push(wn.to_array());
            self.col.push(color(lp, wp));
        }
        match mesh.indices() {
            Some(Indices::U32(i)) => self.idx.extend(i.iter().map(|v| v + base)),
            Some(Indices::U16(i)) => self.idx.extend(i.iter().map(|v| *v as u32 + base)),
            None => self.idx.extend((0..p.len() as u32).map(|v| v + base)),
        }
    }

    fn build(self) -> Mesh {
        let mut mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default());
        mesh.insert_attribute(Mesh::ATTRIBUTE_POSITION, self.pos);
        mesh.insert_attribute(Mesh::ATTRIBUTE_NORMAL, self.nrm);
        mesh.insert_attribute(Mesh::ATTRIBUTE_COLOR, self.col);
        mesh.insert_indices(Indices::U32(self.idx));
        mesh
    }
}

fn lerp3(a: [f32; 3], b: [f32; 3], t: f32) -> [f32; 3] {
    [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
}

/// A low leafy bush: several lumpy leaf balls, darker underneath.
fn bush_mesh(seed: u32) -> Mesh {
    let ball = Sphere::new(1.0).mesh().ico(2).unwrap();
    let mut b = PropBuilder::default();
    let n = 5 + (hash(seed as i32, 3, 7) * 4.0) as usize;
    for i in 0..n {
        let a = i as f32 / n as f32 * std::f32::consts::TAU + hash(seed as i32, i as i32, 1);
        let r = if i == 0 { 0.0 } else { 0.14 + 0.12 * hash(seed as i32, i as i32, 2) };
        let s = if i == 0 { 0.22 } else { 0.12 + 0.08 * hash(seed as i32, i as i32, 3) };
        let tf = Transform::from_xyz(a.cos() * r, s * 0.5 + if i == 0 { 0.05 } else { 0.0 }, a.sin() * r).with_scale(Vec3::new(s, s * 0.75, s));
        let shade = 0.75 + 0.4 * hash(seed as i32, i as i32, 4);
        let hue = hash(seed as i32, i as i32, 5);
        b.add(
            &ball,
            tf,
            // leafy, irregular outline
            |p| 0.22 * (noise(p.x * 4.0 + 9.0, p.z * 4.0 + p.y * 3.0, 0.3, seed + i as u32) - 0.5),
            |_, wp| {
                let t = (wp.y / 0.32).clamp(0.0, 1.0);
                let top = lerp3([0.13, 0.30, 0.07], [0.22, 0.34, 0.06], hue);
                let c = lerp3([0.03, 0.08, 0.02], top, t * t);
                [c[0] * shade, c[1] * shade, c[2] * shade, 1.0]
            },
        );
    }
    b.build()
}

/// A rounded boulder (desert cobbles, pebbles): a squashed, noisy ico-sphere.
fn stone_mesh(seed: u32, size: f32, flat: f32, light: [f32; 3], dark: [f32; 3], detail: u32) -> Mesh {
    let ball = Sphere::new(1.0).mesh().ico(detail).unwrap();
    let mut b = PropBuilder::default();
    let tint = 0.85 + 0.3 * hash(seed as i32, 5, 9);
    b.add(
        &ball,
        Transform::from_xyz(0.0, size * flat * 0.45, 0.0).with_scale(Vec3::new(size, size * flat, size * (0.8 + 0.3 * hash(seed as i32, 1, 1)))),
        |p| 0.18 * (noise(p.x * 2.0 + 5.0, p.z * 2.0 + p.y * 3.0, 0.7, seed) - 0.5),
        |lp, _| {
            let t = ((lp.y + 1.0) * 0.5).clamp(0.0, 1.0);
            let c = lerp3(dark, light, t);
            [c[0] * tint, c[1] * tint, c[2] * tint, 1.0]
        },
    );
    b.build()
}

/// A cluster of pointed crystal prisms (swamp).
fn crystal_mesh(seed: u32) -> Mesh {
    let prism = Cone { radius: 1.0, height: 1.0 }.mesh().resolution(6).build();
    let column = Cylinder::new(1.0, 1.0).mesh().resolution(6).build();
    let mut b = PropBuilder::default();
    let n = 3 + (hash(seed as i32, 2, 2) * 3.0) as usize;
    for i in 0..n {
        let a = i as f32 / n as f32 * std::f32::consts::TAU + hash(seed as i32, i as i32, 5) * 1.3;
        let r = if i == 0 { 0.0 } else { 0.09 + 0.07 * hash(seed as i32, i as i32, 6) };
        let len = if i == 0 { 0.42 } else { 0.18 + 0.18 * hash(seed as i32, i as i32, 7) };
        let rad = 0.055 + 0.03 * hash(seed as i32, i as i32, 8);
        let tilt = Quat::from_rotation_z((hash(seed as i32, i as i32, 9) - 0.5) * 0.9) * Quat::from_rotation_x((hash(seed as i32, i as i32, 10) - 0.5) * 0.9);
        let base = Vec3::new(a.cos() * r, 0.0, a.sin() * r);
        let up = tilt * Vec3::Y;
        let color = |_: Vec3, wp: Vec3| {
            let t = (wp.y / 0.5).clamp(0.0, 1.0);
            let c = lerp3([0.10, 0.18, 0.30], [0.42, 0.62, 0.80], t);
            [c[0], c[1], c[2], 1.0]
        };
        b.add(&column, Transform::from_translation(base + up * len * 0.5).with_rotation(tilt).with_scale(Vec3::new(rad, len, rad)), |_| 0.0, color);
        b.add(&prism, Transform::from_translation(base + up * (len + rad * 0.9)).with_rotation(tilt).with_scale(Vec3::new(rad, rad * 1.8, rad)), |_| 0.0, color);
    }
    b.build()
}

/// A glossy jelly drop (candy): a soft, squashed blob.
fn jelly_mesh(seed: u32) -> Mesh {
    let ball = Sphere::new(1.0).mesh().ico(3).unwrap();
    let mut b = PropBuilder::default();
    let s = 0.2 + 0.08 * hash(seed as i32, 1, 4);
    b.add(
        &ball,
        Transform::from_xyz(0.0, s * 0.45, 0.0).with_scale(Vec3::new(s, s * 0.7, s * 0.95)),
        |p| 0.05 * (noise(p.x * 2.0 + 3.0, p.z * 2.0, 0.8, seed) - 0.5),
        |lp, _| {
            let t = ((lp.y + 1.0) * 0.5).clamp(0.0, 1.0);
            let c = lerp3([0.25, 0.02, 0.02], [0.62, 0.08, 0.07], t);
            [c[0], c[1], c[2], 1.0]
        },
    );
    b.build()
}

/// A clump of reeds: thin tapering blades leaning out (shores).
fn reed_mesh(seed: u32) -> Mesh {
    let blade = Cone { radius: 1.0, height: 1.0 }.mesh().resolution(4).build();
    let mut b = PropBuilder::default();
    let n = 4 + (hash(seed as i32, 7, 1) * 4.0) as usize;
    for i in 0..n {
        let a = hash(seed as i32, i as i32, 11) * std::f32::consts::TAU;
        let r = 0.06 * hash(seed as i32, i as i32, 12);
        let len = 0.35 + 0.35 * hash(seed as i32, i as i32, 13);
        let lean = Quat::from_rotation_z((hash(seed as i32, i as i32, 14) - 0.5) * 0.6) * Quat::from_rotation_x((hash(seed as i32, i as i32, 15) - 0.5) * 0.6);
        b.add(
            &blade,
            Transform::from_xyz(a.cos() * r, len * 0.5, a.sin() * r).with_rotation(lean).with_scale(Vec3::new(0.022, len, 0.022)),
            |_| 0.0,
            |_, wp| {
                let t = (wp.y / 0.6).clamp(0.0, 1.0);
                let c = lerp3([0.16, 0.20, 0.08], [0.52, 0.50, 0.26], t);
                [c[0], c[1], c[2], 1.0]
            },
        );
    }
    b.build()
}

/// Deterministic per-level random number in 0..1.
fn rnd(x: i32, y: i32, salt: u32, seed: u32) -> f32 {
    hash(x, y, seed.wrapping_add(salt.wrapping_mul(7919)))
}

// ---- spawning -------------------------------------------------------------------------------

#[derive(Component)]
pub struct WaterSurface;

#[derive(Resource)]
struct WaterAnim {
    material: Handle<StandardMaterial>,
    repeats: f32,
}

#[allow(clippy::too_many_arguments)]
pub fn spawn_ground(
    mut commands: Commands,
    sim: Res<GameSim>,
    original: Res<Original>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut terrain_materials: ResMut<Assets<TerrainMaterial>>,
    mut images: ResMut<Assets<Image>>,
) {
    let t0 = std::time::Instant::now();
    let (w, h) = (sim.world.grid.w, sim.world.grid.h);
    let tileset = sim.world.map.tileset.clone();
    let lk = look(&tileset);
    let seed = (sim.world.map.seed as u32).wrapping_mul(2_654_435_761);
    let from_original = original.get().and_then(|o| layers_from_original(&sim, o));
    let source = if from_original.is_some() { "original level art" } else { "level terrain cells" };
    let layers = from_original.unwrap_or_else(|| layers_from_cells(&sim));

    // radar colours (the original interface's radar uses them)
    commands.insert_resource(radar_base(&layers, w, h, &tileset));

    // height field + mesh
    let heights = build_heights(&layers, w, h, seed);
    let mesh = meshes.add(ground_mesh(&heights, w, h));

    // weight map (RGBA = ground, bed, rock, vegetation)
    let mut splat_px = Vec::with_capacity(layers.wts.len() * 4);
    for v in &layers.wts {
        splat_px.extend(v.iter().map(|c| (c.clamp(0.0, 1.0) * 255.0 + 0.5) as u8));
    }
    let mut splat = Image::new(
        Extent3d { width: layers.w as u32, height: layers.h as u32, depth_or_array_layers: 1 },
        TextureDimension::D2,
        splat_px,
        TextureFormat::Rgba8Unorm,
        RenderAssetUsages::RENDER_WORLD,
    );
    splat.sampler = clamp_linear_sampler();

    // layer textures
    let names = ["ground", "bed", "rock", "veg"];
    let albedo: Vec<_> = names.iter().filter_map(|l| load_png(&format!("{tileset}_{l}_albedo.png")).or_else(|| load_png(&format!("normal_{l}_albedo.png")))).collect();
    let normal: Vec<_> = names.iter().filter_map(|l| load_png(&format!("{tileset}_{l}_normal.png")).or_else(|| load_png(&format!("normal_{l}_normal.png")))).collect();
    let arrays = if albedo.len() == 4 && normal.len() == 4 { texture_array(albedo, true).zip(texture_array(normal, false)) } else { None };
    let Some((albedo, normal)) = arrays else {
        error!("terrain textures missing in assets/textures/terrain: the ground stays flat grey");
        let mat = materials.add(StandardMaterial { base_color: Color::srgb(0.45, 0.42, 0.36), perceptual_roughness: 0.95, ..default() });
        commands.spawn((DespawnOnExit(AppState::InGame), Name::new("Ground"), Mesh3d(mesh), MeshMaterial3d(mat)));
        commands.insert_resource(heights);
        return;
    };
    let terrain = terrain_materials.add(TerrainMaterial {
        base: StandardMaterial { base_color: Color::WHITE, perceptual_roughness: 0.9, reflectance: 0.3, ..default() },
        extension: TerrainExt {
            params: TerrainParams {
                map: Vec4::new(w as f32, h as f32, 1.0 / 3.0, 4.0),
                roughness: lk.roughness,
                normal_strength: lk.normal_strength,
                layer_scale: lk.layer_scale,
                water: Vec4::new(WATER_LEVEL, LAKE_DEPTH * 0.7, 0.42, 0.62),
            },
            splat: images.add(splat),
            albedo: images.add(albedo),
            normal: images.add(normal),
        },
    });
    commands.spawn((DespawnOnExit(AppState::InGame), Name::new("Ground"), Mesh3d(mesh), MeshMaterial3d(terrain)));

    // water: one surface over the whole map; the ground covers it everywhere except the lakes
    let size = Vec2::new(w as f32 + 2.0 * APRON as f32, h as f32 + 2.0 * APRON as f32);
    let water_mesh = Plane3d::default().mesh().size(size.x, size.y).build().with_generated_tangents().ok();
    let ripples = load_png("water_ripples_normal.png").map(|(rw, rh, px)| {
        let mut img = Image::new_uninit(Extent3d { width: rw, height: rh, depth_or_array_layers: 1 }, TextureDimension::D2, TextureFormat::Rgba8Unorm, RenderAssetUsages::RENDER_WORLD);
        let chain = mip_chain(rw, rh, px);
        img.texture_descriptor.mip_level_count = chain.len() as u32;
        img.data = Some(chain.concat());
        img.sampler = repeat_sampler();
        images.add(img)
    });
    if let Some(wm) = water_mesh {
        let repeats = size.x.max(size.y) / 10.0;
        let [r, g, b, _] = lk.water.to_srgba().to_f32_array();
        let water = materials.add(StandardMaterial {
            base_color: Color::srgba(r, g, b, lk.water_alpha),
            alpha_mode: AlphaMode::Blend,
            perceptual_roughness: 0.07,
            reflectance: 0.55,
            normal_map_texture: ripples,
            uv_transform: Affine2::from_scale(Vec2::splat(repeats)),
            ..default()
        });
        commands.spawn((
            DespawnOnExit(AppState::InGame),
            WaterSurface,
            NotShadowCaster,
            Name::new("Water"),
            Mesh3d(meshes.add(wm)),
            MeshMaterial3d(water.clone()),
            Transform::from_xyz(w as f32 * 0.5, WATER_LEVEL, h as f32 * 0.5),
        ));
        commands.insert_resource(WaterAnim { material: water, repeats });
    }

    // props
    let props = spawn_props(&mut commands, &layers, &heights, &lk, w, h, seed, &mut meshes, &mut materials);
    info!(
        "3-D ground built from the {source}: {}x{} cells, {} props, {:.0} ms",
        w,
        h,
        props,
        t0.elapsed().as_secs_f32() * 1000.0
    );
    commands.insert_resource(heights);
}

#[allow(clippy::too_many_arguments)]
fn spawn_props(
    commands: &mut Commands,
    layers: &LayerMap,
    gh: &GroundHeight,
    lk: &Look,
    w: i32,
    h: i32,
    seed: u32,
    meshes: &mut Assets<Mesh>,
    materials: &mut Assets<StandardMaterial>,
) -> usize {
    // a few variants of each prop (instanced by Bevy: same mesh + material = one batch)
    let variants = 4u32;
    let (veg_meshes, veg_mat): (Vec<Handle<Mesh>>, Handle<StandardMaterial>) = match lk.veg {
        VegKind::Bush => ((0..variants).map(|i| meshes.add(bush_mesh(seed + i))).collect(), materials.add(StandardMaterial { perceptual_roughness: 0.95, reflectance: 0.2, ..default() })),
        VegKind::Boulder => (
            (0..variants).map(|i| meshes.add(stone_mesh(seed + i, 0.28, 0.6, [0.40, 0.31, 0.24], [0.15, 0.11, 0.09], 2))).collect(),
            materials.add(StandardMaterial { perceptual_roughness: 0.8, ..default() }),
        ),
        VegKind::Crystal => (
            (0..variants).map(|i| meshes.add(crystal_mesh(seed + i))).collect(),
            materials.add(StandardMaterial { perceptual_roughness: 0.18, reflectance: 0.7, emissive: LinearRgba::rgb(0.01, 0.03, 0.05), ..default() }),
        ),
        VegKind::Jelly => (
            (0..variants).map(|i| meshes.add(jelly_mesh(seed + i))).collect(),
            materials.add(StandardMaterial { perceptual_roughness: 0.12, reflectance: 0.6, ..default() }),
        ),
    };
    let (stone_meshes, stone_mat): (Vec<Handle<Mesh>>, Handle<StandardMaterial>) = match lk.stones {
        StoneKind::Pebble => ((0..variants).map(|i| meshes.add(stone_mesh(seed + 10 + i, 0.1, 0.5, [0.50, 0.47, 0.40], [0.24, 0.22, 0.18], 2))).collect(), materials.add(StandardMaterial { perceptual_roughness: 0.8, ..default() })),
        StoneKind::Gravel => ((0..variants).map(|i| meshes.add(stone_mesh(seed + 10 + i, 0.08, 0.6, [0.50, 0.48, 0.45], [0.26, 0.24, 0.22], 1))).collect(), materials.add(StandardMaterial { perceptual_roughness: 0.85, ..default() })),
        StoneKind::MossTuft => ((0..variants).map(|i| meshes.add(bush_mesh(seed + 20 + i))).collect(), materials.add(StandardMaterial { perceptual_roughness: 0.9, ..default() })),
        StoneKind::Crumb => ((0..variants).map(|i| meshes.add(stone_mesh(seed + 10 + i, 0.08, 0.5, [0.62, 0.45, 0.32], [0.30, 0.20, 0.13], 1))).collect(), materials.add(StandardMaterial { perceptual_roughness: 0.75, ..default() })),
    };
    let reed_meshes: Vec<Handle<Mesh>> = if lk.reeds { (0..variants).map(|i| meshes.add(reed_mesh(seed + 30 + i))).collect() } else { Vec::new() };
    let reed_mat = materials.add(StandardMaterial { perceptual_roughness: 0.8, double_sided: true, cull_mode: None, ..default() });

    let mut count = 0;
    let mut place = |commands: &mut Commands, mesh: &Handle<Mesh>, mat: &Handle<StandardMaterial>, x: f32, z: f32, scale: f32, yaw: f32, shadow: bool| {
        let y = gh.at(x, z);
        let mut e = commands.spawn((DespawnOnExit(AppState::InGame), Mesh3d(mesh.clone()), MeshMaterial3d(mat.clone()), Transform::from_xyz(x, y, z).with_rotation(Quat::from_rotation_y(yaw)).with_scale(Vec3::splat(scale))));
        if !shadow {
            e.insert(NotShadowCaster);
        }
        count += 1;
    };
    // vegetation layer: a jittered grid, denser where the layer is solid
    let step = 0.72;
    let (nx, nz) = ((w as f32 / step) as i32, (h as f32 / step) as i32);
    for iz in 0..nz {
        for ix in 0..nx {
            let x = (ix as f32 + 0.15 + 0.7 * rnd(ix, iz, 1, seed)) * step;
            let z = (iz as f32 + 0.15 + 0.7 * rnd(ix, iz, 2, seed)) * step;
            let [_, bed, rock, veg] = layers.sample(x, z);
            let pick = rnd(ix, iz, 3, seed);
            let vi = (rnd(ix, iz, 4, seed) * variants as f32) as usize % variants as usize;
            let yaw = rnd(ix, iz, 5, seed) * std::f32::consts::TAU;
            if veg > 0.55 && pick < (veg - 0.45) * 1.25 {
                let s = 0.75 + 0.55 * rnd(ix, iz, 6, seed);
                place(commands, &veg_meshes[vi], &veg_mat, x, z, s, yaw, true);
            } else if rock > 0.65 && pick < (rock - 0.6) * 0.3 {
                // a few loose stones: the rock layer's own texture carries the gravel
                let s = 0.6 + 1.1 * rnd(ix, iz, 7, seed);
                place(commands, &stone_meshes[vi], &stone_mat, x, z, s, yaw, lk.stones == StoneKind::MossTuft);
            } else if !reed_meshes.is_empty() && bed > 0.2 && bed < 0.65 && pick < 0.6 {
                let s = 0.8 + 0.5 * rnd(ix, iz, 8, seed);
                place(commands, &reed_meshes[vi], &reed_mat, x, z, s, yaw, true);
            }
        }
    }
    count
}

fn animate_water(time: Res<Time>, anim: Option<Res<WaterAnim>>, mut materials: ResMut<Assets<StandardMaterial>>) {
    let Some(anim) = anim else { return };
    let Some(mut mat) = materials.get_mut(&anim.material) else { return };
    // slow drift of the ripples (a fraction of a texture repeat per second)
    let t = time.elapsed_secs();
    mat.uv_transform = Affine2::from_scale_angle_translation(Vec2::splat(anim.repeats), 0.0, Vec2::new(t * 0.011, t * 0.007));
}
