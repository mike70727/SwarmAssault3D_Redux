//! A sky for reflections. A small procedural cubemap (a blue sky fading to a pale horizon, soft high
//! cloud, a glow where the game's sun stands, the level's own ground colour below the horizon) is
//! filtered on the GPU by Bevy's `GeneratedEnvironmentMapLight`, so metal (the spider colony's
//! chrome bell, the turret guns) and glossy shells reflect sky and ground instead of black.

use bevy::asset::RenderAssetUsages;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat, TextureViewDescriptor, TextureViewDimension};

/// Pixels along a face (a power of two, as the GPU filter needs).
const FACE: u32 = 128;

/// Linear sky colours, relative to the light's intensity (1 = an average patch of sky).
const ZENITH: Vec3 = Vec3::new(0.32, 0.46, 0.86);
const HORIZON: Vec3 = Vec3::new(0.86, 0.89, 0.95);
const CLOUD: Vec3 = Vec3::new(1.05, 1.05, 1.08);

/// f32 -> IEEE half float bits (the values here are small and positive).
fn f16_bits(v: f32) -> u16 {
    let x = v.clamp(0.0, 65504.0);
    if x < 6.2e-5 {
        return 0;
    }
    let bits = x.to_bits();
    let exp = ((bits >> 23) & 0xff) as i32 - 127 + 15;
    ((exp as u32) << 10 | (bits >> 13) & 0x3ff) as u16
}

/// Smooth value noise in [0, 1) on a 3-D lattice (no seams round the cube).
fn noise3(p: Vec3) -> f32 {
    let hash = |x: i32, y: i32, z: i32| {
        let mut h = (x as u32).wrapping_mul(0x8da6_b343) ^ (y as u32).wrapping_mul(0xd816_3841) ^ (z as u32).wrapping_mul(0xcb1a_b31f);
        h ^= h >> 13;
        h = h.wrapping_mul(0x5bd1_e995);
        h ^= h >> 15;
        (h & 0xffff) as f32 / 65536.0
    };
    let f = p.floor();
    let t = p - f;
    let s = t * t * (Vec3::splat(3.0) - 2.0 * t);
    let (x, y, z) = (f.x as i32, f.y as i32, f.z as i32);
    let lerp = |a: f32, b: f32, t: f32| a + (b - a) * t;
    let c = |dx, dy, dz| hash(x + dx, y + dy, z + dz);
    let x00 = lerp(c(0, 0, 0), c(1, 0, 0), s.x);
    let x10 = lerp(c(0, 1, 0), c(1, 1, 0), s.x);
    let x01 = lerp(c(0, 0, 1), c(1, 0, 1), s.x);
    let x11 = lerp(c(0, 1, 1), c(1, 1, 1), s.x);
    lerp(lerp(x00, x10, s.y), lerp(x01, x11, s.y), s.z)
}

/// Radiance seen along world direction `d` (unit vector, y up).
fn radiance(d: Vec3, ground: Vec3, sun: Vec3) -> Vec3 {
    let e = d.y;
    if e >= 0.0 {
        let mut sky = HORIZON.lerp(ZENITH, e.powf(0.55));
        // high cloud, thicker towards the horizon
        let n = noise3(d * 3.0) * 0.65 + noise3(d * 7.0) * 0.35;
        let cloud = ((n - 0.52) / 0.25).clamp(0.0, 1.0) * (1.0 - e).powf(0.7) * 0.75;
        sky = sky.lerp(CLOUD, cloud);
        // the sun's glow (its disk is the directional light's own highlight)
        let c = d.dot(sun).max(0.0);
        sky + Vec3::new(1.0, 0.95, 0.85) * (c.powf(24.0) * 1.6 + c.powf(4.0) * 0.25)
    } else {
        // the ground, lit, fading into haze at the horizon
        let lit = ground * 0.55;
        let haze = HORIZON * 0.75;
        haze.lerp(lit, (1.0 - (e * 14.0).exp()).clamp(0.0, 1.0))
    }
}

/// The cubemap: faces +X, -X, +Y, -Y, +Z, -Z. `ground` is the level's ground colour (sRGB 0..1),
/// `sun` the direction towards the sun (world, y up).
pub fn sky_cubemap(ground_srgb: [f32; 3], sun: Vec3) -> Image {
    let ground = Vec3::from(ground_srgb.map(|c| c.powf(2.2)));
    let sun = sun.normalize_or_zero();
    let mut data = Vec::with_capacity((FACE * FACE * 6 * 8) as usize);
    for face in 0..6 {
        for y in 0..FACE {
            for x in 0..FACE {
                let s = 2.0 * (x as f32 + 0.5) / FACE as f32 - 1.0;
                let t = 2.0 * (y as f32 + 0.5) / FACE as f32 - 1.0;
                let c = match face {
                    0 => Vec3::new(1.0, -t, -s),
                    1 => Vec3::new(-1.0, -t, s),
                    2 => Vec3::new(s, 1.0, t),
                    3 => Vec3::new(s, -1.0, -t),
                    4 => Vec3::new(s, -t, 1.0),
                    _ => Vec3::new(-s, -t, -1.0),
                }
                .normalize();
                // Bevy samples cubemaps with z flipped
                let d = Vec3::new(c.x, c.y, -c.z);
                let r = radiance(d, ground, sun);
                for v in [r.x, r.y, r.z, 1.0] {
                    data.extend_from_slice(&f16_bits(v).to_le_bytes());
                }
            }
        }
    }
    let mut image = Image::new(
        Extent3d { width: FACE, height: FACE, depth_or_array_layers: 6 },
        TextureDimension::D2,
        data,
        TextureFormat::Rgba16Float,
        RenderAssetUsages::RENDER_WORLD,
    );
    image.texture_view_descriptor = Some(TextureViewDescriptor { dimension: Some(TextureViewDimension::Cube), ..default() });
    image
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn half_floats_round_trip_closely() {
        for v in [0.001f32, 0.05, 0.32, 0.86, 1.0, 2.5, 9.0] {
            let b = f16_bits(v);
            let exp = ((b >> 10) & 0x1f) as i32 - 15;
            let back = (1.0 + (b & 0x3ff) as f32 / 1024.0) * 2f32.powi(exp);
            assert!((back - v).abs() / v < 0.002, "{v} -> {back}");
        }
    }

    #[test]
    fn the_sky_is_brighter_than_the_ground_and_glows_round_the_sun() {
        let sun = Vec3::new(-0.5, 0.8, 0.26).normalize();
        let ground = Vec3::new(0.4, 0.3, 0.2);
        let up = radiance(Vec3::Y, ground, sun);
        let down = radiance(Vec3::NEG_Y, ground, sun);
        let at_sun = radiance(sun, ground, sun);
        assert!(up.length() > down.length());
        assert!(at_sun.length() > up.length() * 1.5);
    }
}
