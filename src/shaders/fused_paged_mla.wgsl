// fused_paged_mla.wgsl
// WebGPU compute shader for paged MLA decode with ue8m0 dequantization.
//
// Architecture:
//   - KV cache is split into fixed-size pages (4096 tokens each by default).
//   - A page table maps sequence positions to page IDs.
//   - Keys are stored as ue8m0 (float8_e4m3 mantissa + exponent-biased scale).
//   - Values are stored as f32 for simplicity (f16 possible with extension).

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const PAGE_SIZE: u32 = 4096;
const MAX_PAGES: u32 = 32768;
const D_HEAD: u32 = 128;
const N_HEADS: u32 = 128;
const D_R: u32 = 64;            // rotary key tail (half of d_head)
const BLOCK_M: u32 = 1;         // one query token per invocation
const BLOCK_N: u32 = 1;

// ---------------------------------------------------------------------------
// KVCachePage layout
// ---------------------------------------------------------------------------
struct KVCachePage {
    // Compressed nope latent (no rotary): vec4<u32> for packed ue8m0
    compressed_nope: array<vec4<u32>, 1792>,
    // Decoupled rotary tail: vec4<f32> for explicit f32 rotary embeddings
    decoupled_rope: array<vec4<f32>, 2048>,
    // Per-tile ue8m0 exponent scales: u32 encodes exponent + bias
    ue8m0_scales: array<u32, 128>,
}

// ---------------------------------------------------------------------------
// Shader output
// ---------------------------------------------------------------------------
struct Output {
    result: array<f32>,
}

// ---------------------------------------------------------------------------
// Helper: dequantize a single ue8m0 value
// ---------------------------------------------------------------------------
fn dequantize_e4m3(mantissa: f32, exp_bias: u32) -> f32 {
    let exponent = i32(exp_bias) - 8;
    if (exp_bias == 0u) {
        return mantissa;
    }
    return mantissa * pow(f32(2.0), f32(exponent));
}

// ---------------------------------------------------------------------------
// Helper: fetch the ue8m0 scale for a given page and position
// ---------------------------------------------------------------------------
fn fetch_ue8m0_scale(
    page: KVCachePage,
    tile_idx: u32,
    head_idx: u32,
) -> u32 {
    // Each tile has 128 scales for N_HEADS * D_HEAD positions
    let scale_offset = (head_idx * D_HEAD) + (tile_idx % (D_HEAD / 8));
    return page.ue8m0_scales[scale_offset];
}

// ---------------------------------------------------------------------------
// Input storage
// ---------------------------------------------------------------------------
@group(0) @binding(0)
var<storage, read> pages: array<KVCachePage>;

@group(0) @binding(1)
var<storage, read> page_table: array<u32>;

@group(0) @binding(2)
var<storage, read> query: array<f32>;

@group(0) @binding(3)
var<storage, read> values: array<f32>;

@group(0) @binding(4)
var<storage, read_write> output: Output;

// ---------------------------------------------------------------------------
// Compute shader entry point
// ---------------------------------------------------------------------------
@compute @workgroup_size(64, 1, 1)
fn mla_paged_decode(
    @builtin(global_invocation_id) gid: vec3<u32>,
    @builtin(workgroup_id) wgid: vec3<u32>,
    @builtin(local_invocation_id) lid: vec3<u32>,
    @builtin(num_workgroups) nwg: vec3<u32>,
) {
    let query_idx = gid.x;
    let head_idx = wgid.x % N_HEADS;
    let seq_pos = query_idx;

    // Look up page for this sequence position
    let page_id = page_table[seq_pos / PAGE_SIZE];
    let page_offset = seq_pos % PAGE_SIZE;

    // Bounds check
    if (page_id >= MAX_PAGES) {
        return;
    }

    let page = pages[page_id];

    // Fetch compressed nope and rope tails
    let nope_idx = page_offset / 4u;
    let nope_vec4 = page.compressed_nope[nope_idx];

    let rope_idx = page_offset / 4u;
    let rope_vec4 = page.decoupled_rope[rope_idx];

    // Fetch ue8m0 scale for this head/tile
    let tile_idx = page_offset / (D_HEAD / 8u);
    let scale = fetch_ue8m0_scale(page, tile_idx, head_idx);

    // Dequantize key components
    let nope_dequant = vec4<f32>(
        dequantize_e4m3(f32(nope_vec4.x), u32(scale)),
        dequantize_e4m3(f32(nope_vec4.y), u32(scale)),
        dequantize_e4m3(f32(nope_vec4.z), u32(scale)),
        dequantize_e4m3(f32(nope_vec4.w), u32(scale)),
    );

    // Load query for this head
    let q_head_start = query_idx * (N_HEADS * D_HEAD) + head_idx * D_HEAD;
    var q: vec4<f32> = vec4<f32>(0.0, 0.0, 0.0, 0.0);

    // Simple dot-product attention (unrolled for workgroup size 64)
    var logits: f32 = 0.0;
    let d_head_half = D_HEAD / 2u;

    for (var i: u32 = 0u; i < d_head_half; i = i + 1u) {
        let q_idx = q_head_start + i * 2u;
        let k_idx = head_idx * D_HEAD + i * 2u;
        logits = logits + query[q_idx] * nope_dequant[i * 2u % 4u];
        logits = logits + query[q_idx + 1u] * nope_dequant[(i * 2u + 1u) % 4u];
    }

    // Accumulate across heads (simplified)
    let out_idx = query_idx * (N_HEADS * D_HEAD);
    output.result[out_idx + head_idx] = logits;
}
