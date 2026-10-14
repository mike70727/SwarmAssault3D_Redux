//! The player's own copy of the original Swarm Assault (1999), read at run time the way OpenSA
//! does: graphics and the ground tiles (`Game\Game.DDF`, `Start\Start.DDF`, the loading screens),
//! animations (`Game\Game.ANI`) and sounds (`Game\Game.SDF`, `Start\Start.SDF`).
//!
//! Nothing from the original game ships with Swarm Assault 3D. When a copy is found (settings
//! `original_game_dir`, the `SA_ORIGINAL` variable, or an `original_game\Swarm Assault` folder next
//! to or above the game folder) the game uses its ground, interface, effects and sounds; without
//! one every system falls back to the game's own assets.
//!
//! File formats as documented by OpenSA (OpenRA.Mods.OpenSA: DdfPackage.cs, DdfLoader.cs,
//! SdfPackage.cs, SdfLoader.cs, PaletteFromDdf.cs, MapImporter.cs).

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use bevy::asset::RenderAssetUsages;
use bevy::image::{ImageSampler, ImageSamplerDescriptor};
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};

fn u32_at(d: &[u8], p: usize) -> Option<u32> {
    d.get(p..p + 4).map(|b| u32::from_le_bytes([b[0], b[1], b[2], b[3]]))
}

fn i32_at(d: &[u8], p: usize) -> Option<i32> {
    u32_at(d, p).map(|v| v as i32)
}

fn u16_at(d: &[u8], p: usize) -> Option<u16> {
    d.get(p..p + 2).map(|b| u16::from_le_bytes([b[0], b[1]]))
}

fn cstr(b: &[u8]) -> String {
    let end = b.iter().position(|&c| c == 0).unwrap_or(b.len());
    b[..end].iter().map(|&c| c as char).collect()
}

/// An RGBA8 (sRGB) picture decoded from the original files.
#[derive(Clone, Debug)]
pub struct Rgba {
    pub w: u32,
    pub h: u32,
    pub px: Vec<u8>,
}

impl Rgba {
    pub fn new(w: u32, h: u32) -> Self {
        Self { w, h, px: vec![0; (w * h * 4) as usize] }
    }

    /// Copy `src` into this picture at (x, y), alpha-blended over what is there.
    pub fn blit(&mut self, src: &Rgba, x: i32, y: i32) {
        for sy in 0..src.h as i32 {
            let ty = y + sy;
            if ty < 0 || ty >= self.h as i32 {
                continue;
            }
            for sx in 0..src.w as i32 {
                let tx = x + sx;
                if tx < 0 || tx >= self.w as i32 {
                    continue;
                }
                let s = ((sy as u32 * src.w + sx as u32) * 4) as usize;
                let a = src.px[s + 3] as u32;
                if a == 0 {
                    continue;
                }
                let t = ((ty as u32 * self.w + tx as u32) * 4) as usize;
                if a == 255 {
                    self.px[t..t + 4].copy_from_slice(&src.px[s..s + 4]);
                } else {
                    for c in 0..3 {
                        self.px[t + c] = ((src.px[s + c] as u32 * a + self.px[t + c] as u32 * (255 - a)) / 255) as u8;
                    }
                    self.px[t + 3] = self.px[t + 3].max(a as u8);
                }
            }
        }
    }

    /// A rectangle of this picture.
    pub fn crop(&self, x: u32, y: u32, w: u32, h: u32) -> Rgba {
        let mut out = Rgba::new(w, h);
        for row in 0..h.min(self.h.saturating_sub(y)) {
            let s = (((y + row) * self.w + x) * 4) as usize;
            let n = (w.min(self.w.saturating_sub(x)) * 4) as usize;
            let t = (row * w * 4) as usize;
            out.px[t..t + n].copy_from_slice(&self.px[s..s + n]);
        }
        out
    }

    /// Bevy image (sRGB colour, clamped, linear filtering).
    pub fn to_image(&self) -> Image {
        let mut img = Image::new(
            Extent3d { width: self.w, height: self.h, depth_or_array_layers: 1 },
            TextureDimension::D2,
            self.px.clone(),
            TextureFormat::Rgba8UnormSrgb,
            RenderAssetUsages::RENDER_WORLD,
        );
        img.sampler = ImageSampler::linear();
        img
    }

    /// Bevy image with nearest-neighbour sampling (pixel-exact interface art and cursors).
    pub fn to_image_nearest(&self) -> Image {
        let mut img = self.to_image();
        img.sampler = ImageSampler::nearest();
        img
    }
}

struct DdfEntry {
    offset: usize,
    format: u32,
    size: usize,
    w: u32,
    h: u32,
}

/// A `.DDF` picture archive: a 256-colour palette and named 8-bit pictures (raw or run-length
/// encoded rows). Palette index 0 is transparent.
pub struct Ddf {
    data: Vec<u8>,
    palette: [[u8; 3]; 256],
    entries: HashMap<String, DdfEntry>,
}

impl Ddf {
    pub fn open(path: &Path) -> Option<Self> {
        let data = std::fs::read(path).ok()?;
        let count = u32_at(&data, 0)? as usize;
        let mut palette = [[0u8; 3]; 256];
        for (i, p) in palette.iter_mut().enumerate() {
            let o = 8 + i * 4;
            *p = [*data.get(o)?, *data.get(o + 1)?, *data.get(o + 2)?];
        }
        let mut entries = HashMap::new();
        let mut pos = 8 + 1024;
        for _ in 0..count {
            let name = cstr(data.get(pos..pos + 32)?);
            let e = DdfEntry {
                offset: u32_at(&data, pos + 32)? as usize,
                format: u32_at(&data, pos + 36)?,
                size: i32_at(&data, pos + 40)?.max(0) as usize,
                w: i32_at(&data, pos + 44)?.max(0) as u32,
                h: i32_at(&data, pos + 48)?.max(0) as u32,
            };
            entries.entry(name).or_insert(e);
            pos += 52;
        }
        Some(Self { data, palette, entries })
    }

    pub fn contains(&self, name: &str) -> bool {
        self.entries.contains_key(name)
    }

    pub fn size(&self, name: &str) -> Option<(u32, u32)> {
        self.entries.get(name).map(|e| (e.w, e.h))
    }

    pub fn names(&self) -> impl Iterator<Item = &str> {
        self.entries.keys().map(|s| s.as_str())
    }

    /// Palette indices of a picture (0 = transparent).
    fn indices(&self, e: &DdfEntry) -> Option<Vec<u8>> {
        let (w, h) = (e.w as usize, e.h as usize);
        let d = &self.data;
        if e.format == 0 {
            return d.get(e.offset..e.offset + (w * h).min(e.size.max(w * h))).map(|s| s.to_vec());
        }
        let mut px = vec![0u8; w * h];
        for y in 0..h {
            let row = u32_at(d, e.offset + y * 4)? as usize;
            let mut p = e.offset + h * 4 + row;
            let mut x = 0usize;
            loop {
                let n = u16_at(d, p)? as i16;
                p += 2;
                if n == 0 {
                    break;
                }
                if n < 0 {
                    x += (-n) as usize;
                } else {
                    for _ in 0..n {
                        if x < w {
                            px[y * w + x] = *d.get(p)?;
                        }
                        x += 1;
                        p += 1;
                    }
                }
            }
        }
        Some(px)
    }

    /// A picture as RGBA (palette index 0 transparent).
    pub fn rgba(&self, name: &str) -> Option<Rgba> {
        let e = self.entries.get(name)?;
        let idx = self.indices(e)?;
        let mut out = Rgba::new(e.w, e.h);
        for (i, &c) in idx.iter().enumerate() {
            if c != 0 {
                let [r, g, b] = self.palette[c as usize];
                out.px[i * 4..i * 4 + 4].copy_from_slice(&[r, g, b, 255]);
            }
        }
        Some(out)
    }
}

/// One frame of an animation: the picture and its offset from the animation's origin.
#[derive(Clone, Debug)]
pub struct AniFrame {
    pub picture: String,
    pub offset: IVec2,
    pub scripts: Vec<String>,
}

/// `Game.ANI`: named animations (frame lists) over the pictures of `Game.DDF`.
pub struct Ani {
    pub anims: HashMap<String, Vec<AniFrame>>,
}

impl Ani {
    pub fn open(path: &Path) -> Option<Self> {
        let d = std::fs::read(path).ok()?;
        let mut p = 0usize;
        let n = u32_at(&d, p)? as usize;
        p += 4;
        // metas: name, picture name, 3 ints, offset x/y, two lists of named records
        let mut metas: HashMap<String, (String, IVec2)> = HashMap::new();
        for _ in 0..n {
            let name = cstr(d.get(p..p + 32)?);
            let pic = cstr(d.get(p + 32..p + 64)?);
            let ox = i32_at(&d, p + 76)?;
            let oy = i32_at(&d, p + 80)?;
            let n_unk = u32_at(&d, p + 84)? as usize;
            let n_pts = u32_at(&d, p + 88)? as usize;
            p += 92 + n_unk * 80 + n_pts * 72;
            metas.entry(name).or_insert((pic, IVec2::new(ox, oy)));
        }
        let n = u32_at(&d, p)? as usize;
        p += 4;
        let mut anims = HashMap::new();
        for _ in 0..n {
            let name = cstr(d.get(p..p + 32)?);
            let nf = u32_at(&d, p + 32)? as usize;
            p += 36;
            let mut frames = Vec::with_capacity(nf);
            for _ in 0..nf {
                let meta = cstr(d.get(p..p + 32)?);
                let ns = u32_at(&d, p + 40)? as usize;
                p += 44;
                let mut scripts = Vec::with_capacity(ns);
                for i in 0..ns {
                    scripts.push(cstr(d.get(p + 32 * i..p + 32 * i + 32)?));
                }
                p += 32 * ns;
                let (picture, offset) = metas.get(&meta).cloned().unwrap_or((meta, IVec2::ZERO));
                frames.push(AniFrame { picture, offset, scripts });
            }
            anims.entry(name).or_insert(frames);
        }
        Some(Self { anims })
    }
}

/// A sound of a `.SDF` bank as a ready-to-play WAV file.
pub struct SdfSound {
    pub wav: Arc<[u8]>,
    pub seconds: f32,
}

/// `.SDF` sound banks: named PCM sounds (mono or stereo, 8 or 16 bit).
fn read_sdf(path: &Path, out: &mut HashMap<String, Vec<SdfSound>>) -> usize {
    let Ok(d) = std::fs::read(path) else { return 0 };
    let Some(n) = u32_at(&d, 0) else { return 0 };
    let mut p = 4usize;
    let mut count = 0;
    for _ in 0..n {
        let Some(name) = d.get(p..p + 64).map(cstr) else { break };
        let (Some(off), Some(size), Some(ch), Some(rate), Some(bits)) =
            (u32_at(&d, p + 64), u32_at(&d, p + 68), u16_at(&d, p + 74), u32_at(&d, p + 76), u16_at(&d, p + 86))
        else {
            break;
        };
        p += 92;
        let Some(pcm) = d.get(off as usize..off as usize + size as usize) else { continue };
        let block = ch as u32 * (bits as u32 / 8).max(1);
        let mut wav = Vec::with_capacity(44 + pcm.len());
        wav.extend_from_slice(b"RIFF");
        wav.extend_from_slice(&(36 + pcm.len() as u32).to_le_bytes());
        wav.extend_from_slice(b"WAVEfmt ");
        wav.extend_from_slice(&16u32.to_le_bytes());
        wav.extend_from_slice(&1u16.to_le_bytes());
        wav.extend_from_slice(&ch.to_le_bytes());
        wav.extend_from_slice(&rate.to_le_bytes());
        wav.extend_from_slice(&(rate * block).to_le_bytes());
        wav.extend_from_slice(&(block as u16).to_le_bytes());
        wav.extend_from_slice(&bits.to_le_bytes());
        wav.extend_from_slice(b"data");
        wav.extend_from_slice(&(pcm.len() as u32).to_le_bytes());
        wav.extend_from_slice(pcm);
        let seconds = pcm.len() as f32 / (rate.max(1) * block.max(1)) as f32;
        // a few names occur twice (BOUNCE, BOUNCEBOMBEXPLODE): keep every take as a variant
        out.entry(name).or_default().push(SdfSound { wav: wav.into(), seconds });
        count += 1;
    }
    count
}

/// Everything read from the original game.
pub struct OriginalGame {
    pub dir: PathBuf,
    pub game: Ddf,
    pub start: Option<Ddf>,
    pub ani: Option<Ani>,
    pub sounds: HashMap<String, Vec<SdfSound>>,
    /// Loading screens (`Game\Loading0N.DDF`).
    pub loading: Vec<Rgba>,
    /// Title screen (`Start\SwarmAssaultLogo.DDF`).
    pub title: Option<Rgba>,
}

impl OriginalGame {
    fn open(dir: &Path) -> Option<Self> {
        let game = Ddf::open(&dir.join("Game").join("Game.DDF"))?;
        let start = Ddf::open(&dir.join("Start").join("Start.DDF"));
        let ani = Ani::open(&dir.join("Game").join("Game.ANI"));
        let mut sounds = HashMap::new();
        let n_game = read_sdf(&dir.join("Game").join("Game.SDF"), &mut sounds);
        let n_start = read_sdf(&dir.join("Start").join("Start.SDF"), &mut sounds);
        let mut loading = Vec::new();
        for i in 0..3 {
            if let Some(d) = Ddf::open(&dir.join("Game").join(format!("Loading0{i}.DDF")))
                && let Some(p) = d.rgba(&format!("LOADING0{i}"))
            {
                loading.push(p);
            }
        }
        let title = Ddf::open(&dir.join("Start").join("SwarmAssaultLogo.DDF")).and_then(|d| d.rgba("SWARMASSAULTLOGO"));
        info!(
            "original game found at {}: {} pictures, {} animations, {} + {} sounds, {} loading screens",
            dir.display(),
            game.entries.len(),
            ani.as_ref().map(|a| a.anims.len()).unwrap_or(0),
            n_game,
            n_start,
            loading.len()
        );
        Some(Self { dir: dir.to_path_buf(), game, start, ani, sounds, loading, title })
    }

    /// A picture from Game.DDF (or Start.DDF).
    pub fn picture(&self, name: &str) -> Option<Rgba> {
        self.game.rgba(name).or_else(|| self.start.as_ref().and_then(|s| s.rgba(name)))
    }

    /// The frames of an animation of Game.ANI as pictures with their offsets.
    pub fn animation(&self, name: &str) -> Vec<(Rgba, IVec2)> {
        let Some(ani) = &self.ani else { return Vec::new() };
        ani.anims.get(name).map(|frames| frames.iter().filter_map(|f| self.picture(&f.picture).map(|p| (p, f.offset))).collect()).unwrap_or_default()
    }

    pub fn sound(&self, name: &str) -> Option<&[SdfSound]> {
        self.sounds.get(name).map(|v| v.as_slice())
    }
}

/// The original game, when the player has a copy (shared by every system that can use it).
#[derive(Resource, Clone, Default)]
pub struct Original(pub Option<Arc<OriginalGame>>);

impl Original {
    pub fn get(&self) -> Option<&OriginalGame> {
        self.0.as_deref()
    }
}

/// Folders tried, in order, for the original game (the folder that holds `Game\Game.DDF`).
fn candidates(configured: &str) -> Vec<PathBuf> {
    let mut out = Vec::new();
    if !configured.trim().is_empty() {
        out.push(PathBuf::from(configured.trim()));
    }
    if let Ok(p) = std::env::var("SA_ORIGINAL") {
        out.push(PathBuf::from(p));
    }
    let game_dir = crate::user_path("");
    for base in [Some(game_dir.clone()), game_dir.parent().map(|p| p.to_path_buf())].into_iter().flatten() {
        out.push(base.join("original_game").join("Swarm Assault"));
        out.push(base.join("original_game"));
        out.push(base.join("Swarm Assault"));
    }
    for root in ["C:\\Program Files (x86)", "C:\\Program Files", "C:\\Games", "D:\\Games"] {
        out.push(PathBuf::from(root).join("Swarm Assault"));
    }
    out
}

/// Look for the original game; `None` when there is no copy.
pub fn find(configured: &str) -> Option<OriginalGame> {
    if std::env::var("SA_NO_ORIGINAL").is_ok_and(|v| v != "0") {
        info!("SA_NO_ORIGINAL is set: using the game's own assets only");
        return None;
    }
    for dir in candidates(configured) {
        if dir.join("Game").join("Game.DDF").exists()
            && let Some(o) = OriginalGame::open(&dir)
        {
            return Some(o);
        }
    }
    info!("no copy of the original Swarm Assault found (set original_game_dir in settings.ron): using the game's own assets");
    None
}

/// Builds a sampler descriptor for ground textures (trilinear + anisotropic).
pub fn ground_sampler() -> ImageSampler {
    ImageSampler::Descriptor(ImageSamplerDescriptor {
        address_mode_u: bevy::image::ImageAddressMode::ClampToEdge,
        address_mode_v: bevy::image::ImageAddressMode::ClampToEdge,
        mag_filter: bevy::image::ImageFilterMode::Linear,
        min_filter: bevy::image::ImageFilterMode::Linear,
        mipmap_filter: bevy::image::ImageFilterMode::Linear,
        anisotropy_clamp: 16,
        ..default()
    })
}

pub struct OriginalPlugin;

impl Plugin for OriginalPlugin {
    fn build(&self, app: &mut App) {
        let configured = app.world().get_resource::<crate::settings::Settings>().map(|s| s.original_game_dir.clone()).unwrap_or_default();
        let original = find(&configured).map(Arc::new);
        app.insert_resource(Original(original));
    }
}
