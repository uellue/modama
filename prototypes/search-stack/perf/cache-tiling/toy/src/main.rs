//! Toy experiments of cache tiling at bge-small's shapes (12 heads of 32, hidden 384, FFN 1536, T tokens).
//! One thread; every variant uses the same sgemm (matrixmultiply) and the same exp, so only the order of
//! the work differs. Each variant is checked against a float64 reference (first text) and against the
//! first variant (all texts). Times are the median of REPEAT runs.
//!
//!   toy attn B [T]   B texts of T (512) tokens: scores materialised for all B·12 heads (as ONNX Runtime's
//!                    Attention does), materialised per head (1 MB at 512), and tiled with online softmax
//!                    (FlashAttention-2 order) over query blocks BQ and key blocks BK
//!   toy ffn B [T]    FFN up (384→1536), bias, tanh-GELU, down (1536→384): unfused passes, bias+GELU fused,
//!                    and depth-first over token tiles of TT tokens (the tile's 1536-wide rows stay in L1/L2)

use std::time::Instant;

const H: usize = 12;
const DH: usize = 32;
const D: usize = H * DH;
const F: usize = 1536;
const REPEAT: usize = 7;

#[allow(clippy::too_many_arguments)]
fn sgemm(m: usize, k: usize, n: usize, alpha: f32, a: &[f32], rsa: usize, csa: usize, b: &[f32], rsb: usize,
         csb: usize, beta: f32, c: &mut [f32], rsc: usize) {
    assert!(a.len() >= (m - 1) * rsa + (k - 1) * csa + 1 && b.len() >= (k - 1) * rsb + (n - 1) * csb + 1);
    assert!(c.len() >= (m - 1) * rsc + n);
    unsafe {
        matrixmultiply::sgemm(m, k, n, alpha, a.as_ptr(), rsa as isize, csa as isize, b.as_ptr(), rsb as isize,
                              csb as isize, beta, c.as_mut_ptr(), rsc as isize, 1);
    }
}

/// e^x, relative error about 2e-7, branch-free so that loops over it vectorize.
#[inline(always)]
fn exp_f(x: f32) -> f32 {
    let x = if x < -87.3 { -87.3 } else { x };
    let x = if x > 88.0 { 88.0 } else { x };
    let n = (x * std::f32::consts::LOG2_E + 12582912.0) - 12582912.0;
    let r = x - n * 0.693_145_75 - n * 1.428_606_8e-6;
    let p = 1.0 + r * (1.0 + r * (0.5 + r * (0.166_666_67 + r * (0.041_666_668 + r * (0.008_333_334 + r * 0.001_388_889)))));
    // n is integral and within [-126, 127] after the clamp; the cast without saturation vectorizes
    let ni = unsafe { n.to_int_unchecked::<i32>() };
    p * f32::from_bits(((ni + 127) << 23) as u32)
}

// AVX2/FMA versions of the same exp (the crate is built with target-cpu=native; this VM has AVX2 and FMA)
use std::arch::x86_64::*;

#[inline(always)]
unsafe fn exp8(x: __m256) -> __m256 {
    unsafe {
        let s = _mm256_set1_ps;
        let x = _mm256_min_ps(_mm256_max_ps(x, s(-87.3)), s(88.0));
        let n = _mm256_round_ps::<{ _MM_FROUND_TO_NEAREST_INT | _MM_FROUND_NO_EXC }>(_mm256_mul_ps(x, s(std::f32::consts::LOG2_E)));
        let r = _mm256_fnmadd_ps(n, s(1.428_606_8e-6), _mm256_fnmadd_ps(n, s(0.693_145_75), x));
        let mut p = s(0.001_388_889);
        for c in [0.008_333_334, 0.041_666_668, 0.166_666_67, 0.5, 1.0, 1.0] {
            p = _mm256_fmadd_ps(p, r, s(c));
        }
        let e = _mm256_slli_epi32::<23>(_mm256_add_epi32(_mm256_cvtps_epi32(n), _mm256_set1_epi32(127)));
        _mm256_mul_ps(p, _mm256_castsi256_ps(e))
    }
}

#[inline(always)]
unsafe fn hsum(v: __m256) -> f32 {
    let mut a = [0f32; 8];
    unsafe { _mm256_storeu_ps(a.as_mut_ptr(), v) };
    a.iter().sum()
}

fn row_max(s: &[f32]) -> f32 {
    let mut it = s.chunks_exact(8);
    let mut a = [f32::NEG_INFINITY; 8];
    unsafe {
        let mut m = _mm256_set1_ps(f32::NEG_INFINITY);
        for c in &mut it {
            m = _mm256_max_ps(m, _mm256_loadu_ps(c.as_ptr()));
        }
        _mm256_storeu_ps(a.as_mut_ptr(), m);
    }
    it.remainder().iter().chain(a.iter()).fold(f32::NEG_INFINITY, |a, &b| a.max(b))
}

/// s ← e^(s − m), returns the sum.
fn exp_sub_sum(s: &mut [f32], m: f32) -> f32 {
    let mut it = s.chunks_exact_mut(8);
    let mut sum = unsafe {
        let (mv, mut acc) = (_mm256_set1_ps(m), _mm256_setzero_ps());
        for c in &mut it {
            let e = exp8(_mm256_sub_ps(_mm256_loadu_ps(c.as_ptr()), mv));
            _mm256_storeu_ps(c.as_mut_ptr(), e);
            acc = _mm256_add_ps(acc, e);
        }
        hsum(acc)
    };
    for v in it.into_remainder() {
        *v = exp_f(*v - m);
        sum += *v;
    }
    sum
}

fn softmax_rows(s: &mut [f32], n: usize) {
    for row in s.chunks_exact_mut(n) {
        let m = row_max(row);
        let inv = 1.0 / exp_sub_sum(row, m);
        row.iter_mut().for_each(|v| *v *= inv);
    }
}

fn rand_vec(n: usize, seed: u64, scale: f32) -> Vec<f32> {
    let mut x = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
    (0..n)
        .map(|_| {
            x = x.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            ((x >> 40) as f32 / (1u64 << 24) as f32 - 0.5) * 2.0 * scale
        })
        .collect()
}

fn median_ms(mut f: impl FnMut()) -> f64 {
    f();
    let mut ts: Vec<f64> = (0..REPEAT)
        .map(|_| {
            let t = Instant::now();
            f();
            t.elapsed().as_secs_f64() * 1e3
        })
        .collect();
    ts.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    ts[REPEAT / 2]
}

fn max_diff(a: &[f32], b: &[f32]) -> f64 {
    a.iter().zip(b).map(|(x, y)| (*x as f64 - *y as f64).abs()).fold(0.0, f64::max)
}

fn max_diff64(a: &[f32], b: &[f64]) -> f64 {
    a.iter().zip(b).map(|(x, y)| (*x as f64 - y).abs()).fold(0.0, f64::max)
}

// ---------------------------------------------------------------- attention; q, k, v, o: [B·H][T][DH]

fn attn_materialised(q: &[f32], k: &[f32], v: &[f32], o: &mut [f32], heads: usize, t: usize, s: &mut [f32],
                     group: usize) {
    // `group` heads' scores at once: group = heads is ONNX Runtime's order, group = 1 one head at a time
    let scale = 1.0 / (DH as f32).sqrt();
    let hs = t * DH;
    for g0 in (0..heads).step_by(group) {
        let g1 = (g0 + group).min(heads);
        for h in g0..g1 {
            let sh = &mut s[(h - g0) * t * t..(h - g0 + 1) * t * t];
            sgemm(t, DH, t, scale, &q[h * hs..], DH, 1, &k[h * hs..], 1, DH, 0.0, sh, t);
        }
        softmax_rows(&mut s[..(g1 - g0) * t * t], t);
        for h in g0..g1 {
            let sh = &s[(h - g0) * t * t..(h - g0 + 1) * t * t];
            sgemm(t, t, DH, 1.0, sh, t, 1, &v[h * hs..], DH, 1, 0.0, &mut o[h * hs..(h + 1) * hs], DH);
        }
    }
}

fn attn_flash(q: &[f32], k: &[f32], v: &[f32], o: &mut [f32], heads: usize, t: usize, bq: usize, bk: usize) {
    let scale = 1.0 / (DH as f32).sqrt();
    let hs = t * DH;
    let mut s = vec![0f32; bq * bk];
    let mut m = vec![0f32; bq];
    let mut l = vec![0f32; bq];
    for h in 0..heads {
        let (qh, kh, vh) = (&q[h * hs..(h + 1) * hs], &k[h * hs..(h + 1) * hs], &v[h * hs..(h + 1) * hs]);
        let oh = &mut o[h * hs..(h + 1) * hs];
        for i0 in (0..t).step_by(bq) {
            let nq = bq.min(t - i0);
            let acc = &mut oh[i0 * DH..(i0 + nq) * DH];
            acc.fill(0.0);
            m[..nq].fill(f32::NEG_INFINITY);
            l[..nq].fill(0.0);
            for j0 in (0..t).step_by(bk) {
                let nk = bk.min(t - j0);
                sgemm(nq, DH, nk, scale, &qh[i0 * DH..], DH, 1, &kh[j0 * DH..], 1, DH, 0.0, &mut s, nk);
                for r in 0..nq {
                    let row = &mut s[r * nk..(r + 1) * nk];
                    let mn = m[r].max(row_max(row));
                    let corr = exp_f(m[r] - mn);
                    l[r] = l[r] * corr + exp_sub_sum(row, mn);
                    m[r] = mn;
                    acc[r * DH..(r + 1) * DH].iter_mut().for_each(|x| *x *= corr);
                }
                sgemm(nq, nk, DH, 1.0, &s, nk, 1, &vh[j0 * DH..], DH, 1, 1.0, acc, DH);
            }
            for r in 0..nq {
                let inv = 1.0 / l[r];
                acc[r * DH..(r + 1) * DH].iter_mut().for_each(|x| *x *= inv);
            }
        }
    }
}

fn attn_reference(q: &[f32], k: &[f32], v: &[f32], t: usize) -> Vec<f64> {
    // the first text's H heads in float64, softmax(Q·Kᵀ/√d)·V
    let scale = 1.0 / (DH as f64).sqrt();
    let mut o = vec![0f64; H * t * DH];
    let mut s = vec![0f64; t];
    for h in 0..H {
        let b = h * t * DH;
        for i in 0..t {
            for j in 0..t {
                s[j] = (0..DH).map(|c| q[b + i * DH + c] as f64 * k[b + j * DH + c] as f64).sum::<f64>() * scale;
            }
            let mx = s.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
            let sum: f64 = s.iter_mut().map(|x| { *x = (*x - mx).exp(); *x }).sum();
            for j in 0..t {
                for c in 0..DH {
                    o[b + i * DH + c] += s[j] / sum * v[b + j * DH + c] as f64;
                }
            }
        }
    }
    o
}

fn run_attn(b: usize, t: usize) {
    let heads = b * H;
    let n = heads * t * DH;
    // scaled like the model's: scores of a few units
    let (q, k, v) = (rand_vec(n, 1, 1.5), rand_vec(n, 2, 1.5), rand_vec(n, 3, 1.0));
    let reference = attn_reference(&q, &k, &v, t);
    let first = H * t * DH;
    let gflop = 4.0 * (heads * t * t * DH) as f64 / 1e9;
    let mut base = vec![0f32; n];
    let mut o = vec![0f32; n];
    let report = |name: &str, ms: f64, o: &[f32], base: &[f32]| {
        println!("attn B={b} T={t} {name:28} {ms:9.2} ms  {:6.2} ms/text  {:6.1} GFLOP/s  vs f64 {:.1e}  vs first {:.1e}",
                 ms / b as f64, gflop / ms * 1e3, max_diff64(&o[..first], &reference), max_diff(o, base));
    };
    let mut s = vec![0f32; heads * t * t];
    let ms = median_ms(|| attn_materialised(&q, &k, &v, &mut base, heads, t, &mut s, heads));
    report(&format!("materialised, all heads ({} MB)", heads * t * t * 4 >> 20), ms, &base, &base);
    for group in [H, 1] {
        if group == heads {
            continue;
        }
        let ms = median_ms(|| attn_materialised(&q, &k, &v, &mut o, heads, t, &mut s, group));
        report(&format!("materialised, {group} head(s) ({} KB)", group * t * t * 4 >> 10), ms, &o, &base);
    }
    // the parts of the per-head order on their own: where the time goes
    let (scale, hs) = (1.0 / (DH as f32).sqrt(), t * DH);
    let sh = &mut s[..t * t];
    let ms_qk = median_ms(|| (0..heads).for_each(|h| sgemm(t, DH, t, scale, &q[h * hs..], DH, 1, &k[h * hs..], 1, DH, 0.0, sh, t)));
    let ms_sm = median_ms(|| (0..heads).for_each(|_| softmax_rows(sh, t)));
    let ms_av = median_ms(|| (0..heads).for_each(|h| sgemm(t, t, DH, 1.0, sh, t, 1, &v[h * hs..], DH, 1, 0.0, &mut o[h * hs..(h + 1) * hs], DH)));
    println!("attn B={b} T={t} parts per head, summed: Q.K^T {ms_qk:.2} ms, softmax {ms_sm:.2} ms, P.V {ms_av:.2} ms");
    for bq in [16, 32, 64, 128, 256] {
        for bk in [32, 64, 128, 256, 512] {
            if bq > t || bk > t {
                continue;
            }
            let ms = median_ms(|| attn_flash(&q, &k, &v, &mut o, heads, t, bq, bk));
            report(&format!("tiled BQ={bq} BK={bk}"), ms, &o, &base);
        }
    }
}

// ---------------------------------------------------------------- FFN; x: [N][D], w1: [D][F], w2: [F][D]

/// The tanh form ONNX Runtime's FastGelu computes, eight at a time; tanh(y) = 1 − 2/(e^(2y) + 1).
#[inline(always)]
unsafe fn gelu8(x: __m256) -> __m256 {
    unsafe {
        let s = _mm256_set1_ps;
        let x3 = _mm256_mul_ps(_mm256_mul_ps(x, x), x);
        let y2 = _mm256_mul_ps(s(2.0 * 0.797_884_6), _mm256_fmadd_ps(x3, s(0.044_715), x));
        let d = _mm256_div_ps(s(2.0), _mm256_add_ps(exp8(y2), s(1.0)));
        _mm256_mul_ps(_mm256_mul_ps(s(0.5), x), _mm256_sub_ps(s(2.0), d))
    }
}

struct Ffn {
    w1: Vec<f32>,
    b1: Vec<f32>,
    w2: Vec<f32>,
    b2: Vec<f32>,
}

impl Ffn {
    fn up(&self, x: &[f32], h: &mut [f32], rows: usize) {
        sgemm(rows, D, F, 1.0, x, D, 1, &self.w1, F, 1, 0.0, h, F);
    }
    fn down(&self, h: &[f32], y: &mut [f32], rows: usize) {
        for r in y.chunks_exact_mut(D).take(rows) {
            r.copy_from_slice(&self.b2);
        }
        sgemm(rows, F, D, 1.0, h, F, 1, &self.w2, D, 1, 1.0, y, D);
    }
    fn unfused(&self, x: &[f32], h: &mut [f32], y: &mut [f32], rows: usize) {
        self.up(x, h, rows);
        for r in h.chunks_exact_mut(F) {
            r.iter_mut().zip(&self.b1).for_each(|(v, b)| *v += b);
        }
        for c in h.chunks_exact_mut(8) {
            unsafe { _mm256_storeu_ps(c.as_mut_ptr(), gelu8(_mm256_loadu_ps(c.as_ptr()))) };
        }
        self.down(h, y, rows);
    }
    fn bias_gelu(&self, h: &mut [f32]) {
        for r in h.chunks_exact_mut(F) {
            for (c, b) in r.chunks_exact_mut(8).zip(self.b1.chunks_exact(8)) {
                unsafe {
                    let x = _mm256_add_ps(_mm256_loadu_ps(c.as_ptr()), _mm256_loadu_ps(b.as_ptr()));
                    _mm256_storeu_ps(c.as_mut_ptr(), gelu8(x));
                }
            }
        }
    }
    fn fused(&self, x: &[f32], h: &mut [f32], y: &mut [f32], rows: usize) {
        self.up(x, h, rows);
        self.bias_gelu(h);
        self.down(h, y, rows);
    }
    fn depth_first(&self, x: &[f32], h: &mut [f32], y: &mut [f32], rows: usize, tt: usize) {
        for i0 in (0..rows).step_by(tt) {
            let n = tt.min(rows - i0);
            let ht = &mut h[..n * F];
            self.up(&x[i0 * D..(i0 + n) * D], ht, n);
            self.bias_gelu(ht);
            self.down(ht, &mut y[i0 * D..(i0 + n) * D], n);
        }
    }
}

fn run_ffn(b: usize, t: usize) {
    let rows = b * t;
    let x = rand_vec(rows * D, 4, 2.0);
    let f = Ffn {
        w1: rand_vec(D * F, 5, 0.1),
        b1: rand_vec(F, 6, 0.1),
        w2: rand_vec(F * D, 7, 0.05),
        b2: rand_vec(D, 8, 0.1),
    };
    // float64 reference of the first 64 rows, exact tanh
    let nr = 64.min(rows);
    let mut reference = vec![0f64; nr * D];
    for r in 0..nr {
        let hrow: Vec<f64> = (0..F)
            .map(|j| {
                let a = (0..D).map(|c| x[r * D + c] as f64 * f.w1[c * F + j] as f64).sum::<f64>() + f.b1[j] as f64;
                0.5 * a * (1.0 + (0.7978845608028654 * (a + 0.044715 * a * a * a)).tanh())
            })
            .collect();
        for c in 0..D {
            reference[r * D + c] = (0..F).map(|j| hrow[j] * f.w2[j * D + c] as f64).sum::<f64>() + f.b2[c] as f64;
        }
    }
    let gflop = 4.0 * (rows * D * F) as f64 / 1e9;
    let mut h = vec![0f32; rows * F];
    let mut base = vec![0f32; rows * D];
    let mut y = vec![0f32; rows * D];
    let report = |name: &str, ms: f64, y: &[f32], base: &[f32]| {
        println!("ffn B={b} T={t} {name:34} {ms:9.2} ms  {:6.2} ms/text  {:6.1} GFLOP/s  vs f64 {:.1e}  vs first {:.1e}",
                 ms / b as f64, gflop / ms * 1e3, max_diff64(&y[..nr * D], &reference), max_diff(y, base));
    };
    let ms = median_ms(|| f.unfused(&x, &mut h, &mut base, rows));
    report(&format!("unfused, H {} MB", rows * F * 4 >> 20), ms, &base, &base);
    let ms = median_ms(|| f.fused(&x, &mut h, &mut y, rows));
    report("bias+GELU fused", ms, &y, &base);
    for tt in [8, 16, 32, 64, 128, 256, 512] {
        if tt >= rows {
            continue;
        }
        let ms = median_ms(|| f.depth_first(&x, &mut h, &mut y, rows, tt));
        report(&format!("depth-first TT={tt} (tile {} KB)", tt * F * 4 >> 10), ms, &y, &base);
    }
    // the parts on their own, at the full size: where the time goes
    let ms_up = median_ms(|| f.up(&x, &mut h, rows));
    let ms_g = median_ms(|| f.bias_gelu(&mut h));
    let ms_down = median_ms(|| f.down(&h, &mut y, rows));
    println!("ffn B={b} T={t} parts: up {ms_up:.2} ms, bias+GELU {ms_g:.2} ms, down {ms_down:.2} ms");
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let b = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(1);
    let t = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(512);
    match args.get(1).map(String::as_str) {
        Some("attn") => run_attn(b, t),
        Some("ffn") => run_ffn(b, t),
        _ => eprintln!("usage: toy attn|ffn [B [T]]"),
    }
}
