// Swarm Assault 3D ground: four tileable PBR layers (ground, water bed, rock, vegetation) blended
// by a per-level weight map with height-based blending, plus a darkening apron outside the map.
import bevy_pbr::render::{
    forward_io::{VertexOutput, FragmentOutput},
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::{apply_pbr_lighting, main_pass_post_lighting_processing},
};

struct TerrainParams {
    // x, y = map size in cells, z = detail texture repeats per cell, w = height-blend sharpness
    map: vec4<f32>,
    // perceptual roughness of the layers: ground, bed, rock, vegetation
    roughness: vec4<f32>,
    // normal-map strength of the layers
    normal_strength: vec4<f32>,
    // texture scale of each layer relative to map.z (breaks up the repetition between layers)
    layer_scale: vec4<f32>,
    // x = water level, y = depth at which the lake bed is darkest, z = darkest factor,
    // w = how dark wet ground at the shore gets
    water: vec4<f32>,
}

@group(constants::MATERIAL_BIND_GROUP) @binding(100) var<uniform> params: TerrainParams;
@group(constants::MATERIAL_BIND_GROUP) @binding(101) var splat_tex: texture_2d<f32>;
@group(constants::MATERIAL_BIND_GROUP) @binding(102) var splat_smp: sampler;
@group(constants::MATERIAL_BIND_GROUP) @binding(103) var albedo_tex: texture_2d_array<f32>;
@group(constants::MATERIAL_BIND_GROUP) @binding(104) var albedo_smp: sampler;
@group(constants::MATERIAL_BIND_GROUP) @binding(105) var normal_tex: texture_2d_array<f32>;
@group(constants::MATERIAL_BIND_GROUP) @binding(106) var normal_smp: sampler;

fn layer_uv(p: vec2<f32>, i: u32) -> vec2<f32> {
    // a different scale and offset per layer so their repetitions do not line up
    let s = params.map.z * params.layer_scale[i];
    var offsets = array<vec2<f32>, 4>(vec2(0.0, 0.0), vec2(0.37, 0.71), vec2(0.13, 0.29), vec2(0.61, 0.07));
    return p * s + offsets[i];
}

@fragment
fn fragment(in: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    var pbr_input = pbr_input_from_standard_material(in, is_front);
    let p = in.world_position.xz;
    let map = params.map.xy;

    // layer weights: r = ground, g = water bed, b = rock, a = vegetation
    let w_map = textureSample(splat_tex, splat_smp, p / map);
    // the water-bed layer only shows under the water: above the water line it is wet ground
    let y = in.world_position.y;
    let under = smoothstep(params.water.x + 0.02, params.water.x - 0.05, y);
    let wet = w_map.g * (1.0 - under);
    let w = vec4(w_map.r + wet, w_map.g * under, w_map.b, w_map.a);

    let uv0 = layer_uv(p, 0u);
    let uv1 = layer_uv(p, 1u);
    let uv2 = layer_uv(p, 2u);
    let uv3 = layer_uv(p, 3u);
    let a0 = textureSample(albedo_tex, albedo_smp, uv0, 0);
    let a1 = textureSample(albedo_tex, albedo_smp, uv1, 1);
    let a2 = textureSample(albedo_tex, albedo_smp, uv2, 2);
    let a3 = textureSample(albedo_tex, albedo_smp, uv3, 3);

    // height blending: where two layers meet, the one whose texture stands higher wins
    let heights = vec4(a0.a, a1.a, a2.a, a3.a);
    var hw = w * (heights + vec4(0.25));
    hw = pow(max(hw, vec4(0.0)), vec4(params.map.w));
    hw = hw / max(hw.x + hw.y + hw.z + hw.w, 1e-5);

    var color = a0.rgb * hw.x + a1.rgb * hw.y + a2.rgb * hw.z + a3.rgb * hw.w;

    // large-scale brightness variation so the tiling is not visible from afar
    let macro_a = textureSample(albedo_tex, albedo_smp, p * 0.021 + vec2(0.17, 0.43), 0).rgb;
    let macro_b = textureSample(albedo_tex, albedo_smp, p * 0.0071 + vec2(0.71, 0.11), 1).rgb;
    let lum = dot(macro_a, vec3(0.33)) * 0.6 + dot(macro_b, vec3(0.33)) * 0.4;
    color = color * (0.86 + 0.28 * clamp(lum * 1.6, 0.0, 1.0));

    // wet ground at the shore is darker; the lake bed darkens with depth
    color = color * mix(1.0, params.water.w, clamp(wet * 1.6, 0.0, 1.0));
    let depth = clamp((params.water.x - y) / params.water.y, 0.0, 1.0);
    color = color * mix(1.0, params.water.z, depth);

    // outside the map the ground fades into the dark
    let outside = max(max(-p.x, p.x - map.x), max(-p.y, p.y - map.y));
    color = color * mix(1.0, 0.18, smoothstep(0.0, 5.0, outside));

    // normal mapping: tangent space x = +X (u), y = +Z (v), z = up
    let n0 = textureSample(normal_tex, normal_smp, uv0, 0).xyz * 2.0 - 1.0;
    let n1 = textureSample(normal_tex, normal_smp, uv1, 1).xyz * 2.0 - 1.0;
    let n2 = textureSample(normal_tex, normal_smp, uv2, 2).xyz * 2.0 - 1.0;
    let n3 = textureSample(normal_tex, normal_smp, uv3, 3).xyz * 2.0 - 1.0;
    let s = params.normal_strength;
    let nt = vec3(
        n0.xy * s.x * hw.x + n1.xy * s.y * hw.y + n2.xy * s.z * hw.z + n3.xy * s.w * hw.w,
        1.0,
    );
    let N0 = normalize(in.world_normal);
    let T = normalize(vec3(1.0, 0.0, 0.0) - N0 * N0.x);
    let B = cross(T, N0);
    let N = normalize(T * nt.x + B * nt.y + N0 * nt.z);

    pbr_input.material.base_color = vec4(color * pbr_input.material.base_color.rgb, 1.0);
    pbr_input.material.perceptual_roughness = clamp(dot(hw, params.roughness), 0.05, 1.0);
    pbr_input.N = N;

    var out: FragmentOutput;
    out.color = apply_pbr_lighting(pbr_input);
    out.color = main_pass_post_lighting_processing(pbr_input, out.color);
    return out;
}
