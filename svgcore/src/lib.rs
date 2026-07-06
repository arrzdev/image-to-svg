//! svgcore: the hot geometry layer of the image->svg engine, in Rust.
//!
//! Ports the validated Python implementations (backend/postprocess.py,
//! backend/schneider.py) of: path parsing/sampling, Douglas-Peucker,
//! Schneider least-squares cubic fitting, and d-string emission.
//! Pure-Python Schneider was rejected at 12x too slow; its few-curves-per-
//! contour output is exactly the low-point/high-fidelity corner the engine
//! targets, so this port un-rejects it.

use pyo3::prelude::*;

type P = [f64; 2];

#[inline]
fn sub(a: P, b: P) -> P { [a[0] - b[0], a[1] - b[1]] }
#[inline]
fn add(a: P, b: P) -> P { [a[0] + b[0], a[1] + b[1]] }
#[inline]
fn scale(a: P, s: f64) -> P { [a[0] * s, a[1] * s] }
#[inline]
fn dot(a: P, b: P) -> f64 { a[0] * b[0] + a[1] * b[1] }
#[inline]
fn norm(a: P) -> f64 { dot(a, a).sqrt() }
#[inline]
fn normalize(a: P) -> P {
    let n = norm(a);
    if n > 1e-12 { scale(a, 1.0 / n) } else { a }
}

// ----------------------------------------------------------------- parsing

/// Tokenize + sample an SVG path `d` (abs/rel M,L,C,Z; others -> None).
/// Returns list of (points, closed) subpaths with cubics sampled 8x.
fn parse_subpaths(d: &str) -> Option<Vec<(Vec<P>, bool)>> {
    let samples_per_curve = 8usize;
    let mut subpaths: Vec<(Vec<P>, bool)> = Vec::new();
    let mut pts: Vec<P> = Vec::new();
    let mut cur: P = [0.0, 0.0];
    let bytes = d.as_bytes();
    let mut i = 0usize;
    let n = bytes.len();

    #[derive(Clone, Copy, PartialEq)]
    enum Cmd { M, L, C, Z, None }
    let mut cmd = Cmd::None;
    let mut rel = false;
    let mut started_any = false;

    let mut nums: Vec<f64> = Vec::with_capacity(6);

    macro_rules! flush {
        ($closed:expr) => {
            if pts.len() >= 2 {
                subpaths.push((std::mem::take(&mut pts), $closed));
            } else {
                pts.clear();
            }
        };
    }

    while i < n {
        let c = bytes[i] as char;
        match c {
            'M' | 'm' | 'L' | 'l' | 'C' | 'c' | 'Z' | 'z' => {
                nums.clear();
                rel = c.is_ascii_lowercase();
                match c.to_ascii_uppercase() {
                    'M' => {
                        flush!(false);
                        cmd = Cmd::M;
                    }
                    'L' => cmd = Cmd::L,
                    'C' => cmd = Cmd::C,
                    'Z' => {
                        flush!(true);
                        cmd = Cmd::Z;
                    }
                    _ => unreachable!(),
                }
                i += 1;
            }
            ' ' | ',' | '\n' | '\r' | '\t' => i += 1,
            _ => {
                // parse a number
                let start = i;
                if bytes[i] == b'+' || bytes[i] == b'-' { i += 1; }
                let mut seen_dot = false;
                let mut seen_e = false;
                while i < n {
                    let b = bytes[i];
                    if b.is_ascii_digit() { i += 1; }
                    else if b == b'.' && !seen_dot && !seen_e { seen_dot = true; i += 1; }
                    else if (b == b'e' || b == b'E') && !seen_e { seen_e = true; i += 1;
                        if i < n && (bytes[i] == b'+' || bytes[i] == b'-') { i += 1; } }
                    else { break; }
                }
                if i == start { return None; } // garbage
                let v: f64 = d[start..i].parse().ok()?;
                nums.push(v);

                match cmd {
                    Cmd::M => {
                        if nums.len() == 2 {
                            let p = if rel && started_any { add(cur, [nums[0], nums[1]]) } else { [nums[0], nums[1]] };
                            cur = p;
                            pts.push(cur);
                            started_any = true;
                            nums.clear();
                            cmd = Cmd::L; // implicit lineto continues (keeps rel flag)
                        }
                    }
                    Cmd::L => {
                        if nums.len() == 2 {
                            let p = if rel { add(cur, [nums[0], nums[1]]) } else { [nums[0], nums[1]] };
                            cur = p;
                            pts.push(cur);
                            nums.clear();
                        }
                    }
                    Cmd::C => {
                        if nums.len() == 6 {
                            let base = if rel { cur } else { [0.0, 0.0] };
                            let p1 = add(base, [nums[0], nums[1]]);
                            let p2 = add(base, [nums[2], nums[3]]);
                            let p3 = add(base, [nums[4], nums[5]]);
                            for k in 1..=samples_per_curve {
                                let t = k as f64 / samples_per_curve as f64;
                                let mt = 1.0 - t;
                                let pt = add(
                                    add(scale(cur, mt * mt * mt), scale(p1, 3.0 * mt * mt * t)),
                                    add(scale(p2, 3.0 * mt * t * t), scale(p3, t * t * t)),
                                );
                                pts.push(pt);
                            }
                            cur = p3;
                            nums.clear();
                        }
                    }
                    _ => return None, // numbers with no/unsupported command
                }
            }
        }
    }
    flush!(false);
    Some(subpaths)
}

// ------------------------------------------------------------ point count

/// Count anchor points in a d string (same semantics as metrics.py).
#[pyfunction]
fn count_points(d: &str) -> usize {
    let mut count = 0usize;
    let mut nums_in_cmd = 0usize;
    let mut divisor = 2usize; // per-point number count for current cmd
    let mut per_unit = 1usize;
    for tok in d.split(|ch: char| ch == ' ' || ch == ',' || ch == '\n') {
        if tok.is_empty() { continue; }
        let first = tok.chars().next().unwrap();
        if first.is_ascii_alphabetic() {
            let c = first.to_ascii_lowercase();
            (divisor, per_unit) = match c {
                'm' | 'l' | 't' => (2, 1),
                'h' | 'v' => (1, 1),
                's' | 'q' => (4, 1),
                'c' => (6, 1),
                'a' => (7, 1),
                _ => (usize::MAX, 0),
            };
            nums_in_cmd = 0;
            // command letter may be glued to a number (vtracer: "M0")
            if tok.len() > 1 && divisor != usize::MAX {
                nums_in_cmd += 1;
                if nums_in_cmd == divisor { count += per_unit; nums_in_cmd = 0; }
            }
        } else if divisor != usize::MAX {
            nums_in_cmd += 1;
            if nums_in_cmd == divisor { count += per_unit; nums_in_cmd = 0; }
        }
    }
    count
}

// -------------------------------------------------------- douglas-peucker

fn dp_simplify(pts: &[P], eps: f64) -> Vec<P> {
    if pts.len() <= 2 || eps <= 0.0 {
        return pts.to_vec();
    }
    let mut keep = vec![false; pts.len()];
    keep[0] = true;
    *keep.last_mut().unwrap() = true;
    let mut stack = vec![(0usize, pts.len() - 1)];
    while let Some((a, b)) = stack.pop() {
        if b <= a + 1 { continue; }
        let pa = pts[a];
        let pb = pts[b];
        let ab = sub(pb, pa);
        let ab_len = norm(ab);
        let mut max_d = -1.0f64;
        let mut max_i = a;
        for i in (a + 1)..b {
            let dist = if ab_len < 1e-12 {
                norm(sub(pts[i], pa))
            } else {
                ((pts[i][0] - pa[0]) * ab[1] - (pts[i][1] - pa[1]) * ab[0]).abs() / ab_len
            };
            if dist > max_d { max_d = dist; max_i = i; }
        }
        if max_d > eps {
            keep[max_i] = true;
            stack.push((a, max_i));
            stack.push((max_i, b));
        }
    }
    pts.iter().zip(keep.iter()).filter(|(_, k)| **k).map(|(p, _)| *p).collect()
}

// ------------------------------------------------------------- schneider

fn bezier_point(ctrl: &[P; 4], t: f64) -> P {
    let mt = 1.0 - t;
    add(
        add(scale(ctrl[0], mt * mt * mt), scale(ctrl[1], 3.0 * mt * mt * t)),
        add(scale(ctrl[2], 3.0 * mt * t * t), scale(ctrl[3], t * t * t)),
    )
}

fn chord_lengths(pts: &[P]) -> Vec<f64> {
    let mut u = vec![0.0; pts.len()];
    for i in 1..pts.len() {
        u[i] = u[i - 1] + norm(sub(pts[i], pts[i - 1]));
    }
    let total = *u.last().unwrap();
    if total > 1e-12 {
        for v in u.iter_mut() { *v /= total; }
    } else {
        for (i, v) in u.iter_mut().enumerate() { *v = i as f64 / (pts.len() - 1) as f64; }
    }
    u
}

fn generate_bezier(pts: &[P], u: &[f64], t1: P, t2: P) -> [P; 4] {
    let first = pts[0];
    let last = *pts.last().unwrap();
    let mut c = [[0.0f64; 2]; 2];
    let mut x = [0.0f64; 2];
    for (i, &ui) in u.iter().enumerate() {
        let mt = 1.0 - ui;
        let b1 = 3.0 * mt * mt * ui;
        let b2 = 3.0 * mt * ui * ui;
        let a0 = scale(t1, b1);
        let a1 = scale(t2, b2);
        let b0 = mt * mt * mt;
        let b3 = ui * ui * ui;
        let base = add(scale(first, b0 + b1), scale(last, b2 + b3));
        let tmp = sub(pts[i], base);
        c[0][0] += dot(a0, a0);
        c[0][1] += dot(a0, a1);
        c[1][1] += dot(a1, a1);
        x[0] += dot(a0, tmp);
        x[1] += dot(a1, tmp);
    }
    c[1][0] = c[0][1];
    let det = c[0][0] * c[1][1] - c[0][1] * c[1][0];
    let (mut al, mut ar) = (0.0, 0.0);
    if det.abs() > 1e-12 {
        al = (x[0] * c[1][1] - x[1] * c[0][1]) / det;
        ar = (c[0][0] * x[1] - c[1][0] * x[0]) / det;
    }
    let seg_len = norm(sub(last, first));
    let eps = 1e-6 * seg_len;
    // Guard BOTH directions: tiny/negative alphas (degenerate) AND huge ones
    // (near-singular normal equations shoot control points across the canvas,
    // rendering as rogue spikes/wedges).
    let max_alpha = seg_len * 3.0 + 1e-6;
    if al < eps || ar < eps || al > max_alpha || ar > max_alpha {
        al = seg_len / 3.0;
        ar = al;
    }
    [first, add(first, scale(t1, al)), add(last, scale(t2, ar)), last]
}

fn max_error(pts: &[P], ctrl: &[P; 4], u: &[f64]) -> (f64, usize) {
    let mut max_d = 0.0;
    let mut idx = 0;
    for (i, &ui) in u.iter().enumerate() {
        let d = sub(bezier_point(ctrl, ui), pts[i]);
        let dd = dot(d, d);
        if dd > max_d { max_d = dd; idx = i; }
    }
    (max_d.sqrt(), idx)
}

fn reparameterize(pts: &[P], ctrl: &[P; 4], u: &[f64]) -> Vec<f64> {
    let d1 = [
        scale(sub(ctrl[1], ctrl[0]), 3.0),
        scale(sub(ctrl[2], ctrl[1]), 3.0),
        scale(sub(ctrl[3], ctrl[2]), 3.0),
    ];
    let d2 = [
        scale(sub(d1[1], d1[0]), 2.0),
        scale(sub(d1[2], d1[1]), 2.0),
    ];
    u.iter().enumerate().map(|(i, &t)| {
        let pt = bezier_point(ctrl, t);
        let mt = 1.0 - t;
        let q1 = add(add(scale(d1[0], mt * mt), scale(d1[1], 2.0 * mt * t)), scale(d1[2], t * t));
        let q2 = add(scale(d2[0], mt), scale(d2[1], t));
        let diff = sub(pt, pts[i]);
        let num = dot(diff, q1);
        let den = dot(q1, q1) + dot(diff, q2);
        let nt = if den.abs() > 1e-12 { t - num / den } else { t };
        nt.clamp(0.0, 1.0)
    }).collect()
}

fn fit_cubic(pts: &[P], t1: P, t2: P, tol: f64, depth: u32, out: &mut Vec<[P; 4]>) {
    if pts.len() == 2 {
        let seg = norm(sub(pts[1], pts[0])) / 3.0;
        out.push([pts[0], add(pts[0], scale(t1, seg)), add(pts[1], scale(t2, seg)), pts[1]]);
        return;
    }
    let mut u = chord_lengths(pts);
    let mut ctrl = generate_bezier(pts, &u, t1, t2);
    let (mut err, mut split) = max_error(pts, &ctrl, &u);
    if err < tol {
        out.push(ctrl);
        return;
    }
    if err < tol * 4.0 {
        for _ in 0..4 {
            u = reparameterize(pts, &ctrl, &u);
            ctrl = generate_bezier(pts, &u, t1, t2);
            let (e, s) = max_error(pts, &ctrl, &u);
            err = e; split = s;
            if err < tol {
                out.push(ctrl);
                return;
            }
        }
    }
    if depth > 24 || split == 0 || split >= pts.len() - 1 {
        // Forced accept. If the fit is WILD (err >> tol), a bad cubic renders
        // as a rogue spike/wedge — degrade to safe polyline segments instead.
        if err > tol * 4.0 {
            let step = (pts.len() / 8).max(1);
            let mut i = 0;
            while i + step < pts.len() {
                let a = pts[i];
                let b = pts[(i + step).min(pts.len() - 1)];
                let d = scale(sub(b, a), 1.0 / 3.0);
                out.push([a, add(a, d), sub(b, d), b]);
                i += step;
            }
            let a = pts[i.min(pts.len() - 1)];
            let b = *pts.last().unwrap();
            if norm(sub(b, a)) > 1e-9 {
                let d = scale(sub(b, a), 1.0 / 3.0);
                out.push([a, add(a, d), sub(b, d), b]);
            }
        } else {
            out.push(ctrl);
        }
        return;
    }
    let t_center = normalize(sub(pts[split - 1], pts[split + 1]));
    fit_cubic(&pts[..=split], t1, t_center, tol, depth + 1, out);
    fit_cubic(&pts[split..], scale(t_center, -1.0), t2, tol, depth + 1, out);
}

fn find_corners(pts: &[P], corner_deg: f64, win: usize) -> Vec<usize> {
    let n = pts.len();
    if n < 2 * win + 1 { return vec![]; }
    let mut dev = vec![0.0f64; n];
    for i in 0..n {
        let prev = pts[(i + n - win) % n];
        let next = pts[(i + win) % n];
        let a = sub(pts[i], prev);
        let b = sub(next, pts[i]);
        let na = norm(a);
        let nb = norm(b);
        if na > 1e-9 && nb > 1e-9 {
            let cosang = (dot(a, b) / (na * nb)).clamp(-1.0, 1.0);
            dev[i] = cosang.acos().to_degrees();
        }
    }
    let mut corners = Vec::new();
    for i in 0..n {
        if dev[i] > corner_deg {
            let mut is_max = true;
            for k in 0..(2 * win + 1) {
                let j = (i + n + k - win) % n;
                if dev[j] > dev[i] { is_max = false; break; }
            }
            if is_max { corners.push(i); }
        }
    }
    corners
}

fn fmt(v: f64) -> String {
    let s = format!("{:.2}", v);
    s
}

fn emit_closed(curves: &[[P; 4]]) -> String {
    let mut d = format!("M {} {} ", fmt(curves[0][0][0]), fmt(curves[0][0][1]));
    for c in curves {
        d.push_str(&format!(
            "C {} {} {} {} {} {} ",
            fmt(c[1][0]), fmt(c[1][1]), fmt(c[2][0]), fmt(c[2][1]), fmt(c[3][0]), fmt(c[3][1])
        ));
    }
    d.push('Z');
    d
}

fn shoelace_signed(pts: &[P]) -> f64 {
    let n = pts.len();
    let mut area = 0.0;
    for i in 0..n {
        let j = (i + 1) % n;
        area += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1];
    }
    area * 0.5
}

fn shoelace(pts: &[P]) -> f64 {
    shoelace_signed(pts).abs()
}

/// Schneider-fit one closed dense polyline -> d string.
/// Returns None when the fit is INVALID (area mismatch => the curve chain
/// self-intersected / winding flipped — renders as unfilled regions).
fn fit_closed_poly(pts: &[P], tol: f64, corner_deg: f64) -> Option<String> {
    let n = pts.len();
    if n < 3 { return None; }
    let mut corners = find_corners(pts, corner_deg, 3);
    if corners.is_empty() { corners.push(0); }
    let mut curves: Vec<[P; 4]> = Vec::new();
    let m = corners.len();
    for ci in 0..m {
        let a = corners[ci];
        let b = corners[(ci + 1) % m];
        let mut seg: Vec<P> = Vec::new();
        if b > a {
            seg.extend_from_slice(&pts[a..=b]);
        } else {
            seg.extend_from_slice(&pts[a..]);
            seg.extend_from_slice(&pts[..=b]);
        }
        if seg.len() < 2 { continue; }
        let t1 = normalize(sub(seg[1.min(seg.len() - 1)], seg[0]));
        let t2 = normalize(sub(seg[seg.len() - 2], seg[seg.len() - 1]));
        fit_cubic(&seg, t1, t2, tol, 0, &mut curves);
    }
    if curves.is_empty() { return None; }

    // Validity: sample the fitted chain and compare SIGNED area + perimeter-
    // scaled absolute area against the source polygon. Self-intersections and
    // runaway curves show up as area drift.
    let mut sampled: Vec<P> = Vec::with_capacity(curves.len() * 6);
    for c in &curves {
        for k in 0..6 {
            sampled.push(bezier_point(c, k as f64 / 6.0));
        }
    }
    // SIGNED comparison: an orientation-reversed chain has the same |area|
    // but flips hole/fill winding in compound paths — signed catches both
    // drift and reversal.
    let a_src = shoelace_signed(pts);
    let a_fit = shoelace_signed(&sampled);
    let tol_area = (a_src.abs() * 0.18).max(tol * tol * 16.0);
    if (a_fit - a_src).abs() > tol_area {
        return None;
    }
    Some(emit_closed(&curves))
}

// ------------------------------------------------------------- public API

/// Simplify one path d-string: parse, (optional pre-DP), Schneider-fit closed
/// subpaths. Returns None for unsupported commands.
#[pyfunction]
#[pyo3(signature = (d, tol, min_area=4.0, corner_deg=60.0))]
fn simplify_path(d: &str, tol: f64, min_area: f64, corner_deg: f64) -> Option<String> {
    let subs = parse_subpaths(d)?;
    let mut out: Vec<String> = Vec::new();
    for (pts, closed) in subs {
        if closed {
            if shoelace(&pts) < min_area { continue; }
            // Fit the DENSE samples directly (like the validated Python) —
            // pre-DP sparsifies segments and destabilizes the least squares.
            if let Some(s) = fit_closed_poly(&pts, tol, corner_deg) {
                out.push(s);
            } else {
                // Invalid fit (area drift / self-intersection): NEVER drop the
                // region — emit a safe DP polygon instead.
                let reduced = dp_simplify(&pts, tol.max(0.5));
                if reduced.len() >= 3 {
                    let mut s = format!("M {} {} ", fmt(reduced[0][0]), fmt(reduced[0][1]));
                    for p in &reduced[1..] {
                        s.push_str(&format!("L {} {} ", fmt(p[0]), fmt(p[1])));
                    }
                    s.push('Z');
                    out.push(s);
                }
            }
        } else if pts.len() >= 2 {
            let reduced = dp_simplify(&pts, tol);
            let mut s = format!("M {} {} ", fmt(reduced[0][0]), fmt(reduced[0][1]));
            for p in &reduced[1..] {
                s.push_str(&format!("L {} {} ", fmt(p[0]), fmt(p[1])));
            }
            out.push(s.trim_end().to_string());
        }
    }
    Some(out.join(" "))
}


/// Fit an OPEN polyline chain with Schneider cubics; corners split segments;
/// endpoints are preserved exactly (junction-safe). Input [x0,y0,x1,y1,...];
/// output flat cubics: [p0x,p0y,c1x,c1y,c2x,c2y,p3x,p3y] * n.
#[pyfunction]
#[pyo3(signature = (flat, tol, corner_deg=60.0))]
fn fit_open(flat: Vec<f64>, tol: f64, corner_deg: f64) -> Vec<f64> {
    let n = flat.len() / 2;
    if n < 2 { return vec![]; }
    let pts: Vec<P> = (0..n).map(|i| [flat[2 * i], flat[2 * i + 1]]).collect();
    if n == 2 {
        let d = scale(sub(pts[1], pts[0]), 1.0 / 3.0);
        let c = [pts[0], add(pts[0], d), sub(pts[1], d), pts[1]];
        return c.iter().flat_map(|p| p.to_vec()).collect();
    }
    // corner detection on open chain (endpoints are implicit corners)
    let win = 3.min((n - 1) / 2).max(1);
    let mut cuts = vec![0usize];
    for i in win..(n - win) {
        let a = sub(pts[i], pts[i - win]);
        let b = sub(pts[i + win], pts[i]);
        let (na, nb) = (norm(a), norm(b));
        if na > 1e-9 && nb > 1e-9 {
            let cosang = (dot(a, b) / (na * nb)).clamp(-1.0, 1.0);
            if cosang.acos().to_degrees() > corner_deg {
                if *cuts.last().unwrap() + win <= i {
                    cuts.push(i);
                }
            }
        }
    }
    cuts.push(n - 1);
    let mut curves: Vec<[P; 4]> = Vec::new();
    for w in cuts.windows(2) {
        let seg = &pts[w[0]..=w[1]];
        if seg.len() < 2 { continue; }
        let t1 = normalize(sub(seg[1], seg[0]));
        let t2 = normalize(sub(seg[seg.len() - 2], seg[seg.len() - 1]));
        fit_cubic(seg, t1, t2, tol, 0, &mut curves);
    }
    curves.iter().flat_map(|c| c.iter().flat_map(|p| p.to_vec())).collect()
}

// ----------------------------------------------- parsimony (potrace-style)
//
// Potrace §2.2-2.4 adapted to OPEN junction-to-junction crack polylines:
//   1. minimal-segment polygon via DP over "straight" runs (0.5px L-inf
//      tolerance boxes, constraint-cone reach computation = calc_lon),
//   2. sub-pixel vertex adjustment (least-squares lines of adjacent runs,
//      quadratic-form minimum clamped to the +-0.5 box, endpoints pinned),
//   3. tangent-constrained cubics through edge midpoints (one-parameter
//      alpha family; alpha >= alphamax => polygon corner).
// Wobble below the tolerance band is structurally invisible: it cannot
// create polygon segments, so it cannot create curve wiggles.

#[inline]
fn xprod(a: P, b: P) -> f64 { a[0] * b[1] - a[1] * b[0] }

/// reach[i] = largest j such that the run i..j is "straight" in Potrace's
/// exact sense (paper §2.2.1): not all four axis directions occur, and for
/// every triple i < k < j the point v_k lies within max-distance 1 of the
/// line through v_i, v_j. Constraint-cone method = potrace calc_lon: unit-box
/// corner offsets, points with |q|_inf <= 1 exempt, O(1) per extension.
/// A backward pass enforces the nesting property (potrace's lon[] fixup) so
/// DP segments cannot cross.
fn straight_reach(pts: &[P]) -> Vec<usize> {
    let n = pts.len();
    let mut reach: Vec<usize> = (0..n).collect();
    for i in 0..n.saturating_sub(1) {
        let mut c0: P = [0.0, 0.0];
        let mut c1: P = [0.0, 0.0];
        let mut dirs = [false; 4];
        let mut r = i + 1;
        for j in (i + 1)..n {
            // axis-direction class of step j-1 -> j (spiral guard)
            let sdx = pts[j][0] - pts[j - 1][0];
            let sdy = pts[j][1] - pts[j - 1][1];
            if sdx.abs() > 1e-12 || sdy.abs() > 1e-12 {
                let k = if sdx.abs() >= sdy.abs() {
                    if sdx >= 0.0 { 0 } else { 1 }
                } else if sdy >= 0.0 { 2 } else { 3 };
                dirs[k] = true;
                if dirs == [true; 4] { break; }
            }
            let q = sub(pts[j], pts[i]);
            if xprod(c0, q) < 0.0 || xprod(c1, q) > 0.0 { break; }
            r = j;
            // tighten the cone with point j's unit-box corners; adjacent
            // lattice points impose no constraint (potrace exemption)
            if q[0].abs() > 1.0 || q[1].abs() > 1.0 {
                let off0 = [
                    q[0] + if q[1] >= 0.0 && (q[1] > 0.0 || q[0] < 0.0) { 1.0 } else { -1.0 },
                    q[1] + if q[0] <= 0.0 && (q[0] < 0.0 || q[1] < 0.0) { 1.0 } else { -1.0 },
                ];
                if xprod(c0, off0) >= 0.0 { c0 = off0; }
                let off1 = [
                    q[0] + if q[1] <= 0.0 && (q[1] < 0.0 || q[0] < 0.0) { 1.0 } else { -1.0 },
                    q[1] + if q[0] >= 0.0 && (q[0] > 0.0 || q[1] < 0.0) { 1.0 } else { -1.0 },
                ];
                if xprod(c1, off1) <= 0.0 { c1 = off1; }
            }
        }
        reach[i] = r;
    }
    // nesting fixup: a later start may never reach less far than an earlier
    // one allows (open-chain version of potrace's backward lon pass)
    for i in (0..n.saturating_sub(1)).rev() {
        if reach[i] > reach[i + 1] && reach[i + 1] > i {
            reach[i] = reach[i + 1];
        }
    }
    reach
}

/// Prefix sums for O(1) potrace segment penalties (paper eq. in §2.2.3).
struct SumTab { x: Vec<f64>, y: Vec<f64>, xx: Vec<f64>, xy: Vec<f64>, yy: Vec<f64> }

fn sum_tab(pts: &[P]) -> SumTab {
    let n = pts.len();
    let mut t = SumTab {
        x: vec![0.0; n + 1], y: vec![0.0; n + 1], xx: vec![0.0; n + 1],
        xy: vec![0.0; n + 1], yy: vec![0.0; n + 1],
    };
    for (i, p) in pts.iter().enumerate() {
        t.x[i + 1] = t.x[i] + p[0];
        t.y[i + 1] = t.y[i] + p[1];
        t.xx[i + 1] = t.xx[i] + p[0] * p[0];
        t.xy[i + 1] = t.xy[i] + p[0] * p[1];
        t.yy[i + 1] = t.yy[i] + p[1] * p[1];
    }
    t
}

/// Penalty of segment i..j: |vj-vi| * stddev of point distances to the chord.
fn seg_penalty(t: &SumTab, pts: &[P], i: usize, j: usize) -> f64 {
    let k = (j - i + 1) as f64;
    let ex = (t.x[j + 1] - t.x[i]) / k;
    let ey = (t.y[j + 1] - t.y[i]) / k;
    let exx = (t.xx[j + 1] - t.xx[i]) / k;
    let exy = (t.xy[j + 1] - t.xy[i]) / k;
    let eyy = (t.yy[j + 1] - t.yy[i]) / k;
    let mx = (pts[i][0] + pts[j][0]) / 2.0;
    let my = (pts[i][1] + pts[j][1]) / 2.0;
    let dx = pts[j][0] - pts[i][0];
    let dy = pts[j][1] - pts[i][1];
    let a = exx - 2.0 * mx * ex + mx * mx;
    let b = exy - mx * ey - my * ex + mx * my;
    let c = eyy - 2.0 * my * ey + my * my;
    // sum of squared point-to-chord distances = a*dy^2 - 2b*dx*dy + c*dx^2
    // (potrace penalty3; the paper's rendering hides the sign in its axis
    // convention). P = sqrt(mean cross^2) = |chord| * stddev(dist).
    let s = a * dy * dy - 2.0 * b * dx * dy + c * dx * dx;
    if s > 0.0 { s.sqrt() } else { 0.0 }
}

/// Minimal-segment polygon on an OPEN chain: shortest path 0 -> n-1 in the
/// DAG of possible segments (ties: min summed penalty). Potrace's clipping
/// rule: segment i->j is possible iff the run extended one point each way
/// (clamped at the ends) is still straight. Returns vertex indices.
fn best_polygon_open(pts: &[P]) -> Vec<usize> {
    let n = pts.len();
    if n <= 2 { return (0..n).collect(); }
    let reach = straight_reach(pts);
    let tab = sum_tab(pts);
    const BIG: usize = usize::MAX;
    let mut segs = vec![BIG; n];
    let mut pen = vec![f64::INFINITY; n];
    let mut prev = vec![0usize; n];
    segs[0] = 0;
    pen[0] = 0.0;
    for i in 0..n - 1 {
        if segs[i] == BIG { continue; }
        // clipping: i..j possible iff (i-1)..(j+1) straight (clamped)
        let r = reach[i.saturating_sub(1)];
        let ub = (if r >= n - 1 { n - 1 } else { r - 1 }).max(i + 1);
        for j in (i + 1)..=ub {
            let s = segs[i] + 1;
            let p = pen[i] + seg_penalty(&tab, pts, i, j);
            if s < segs[j] || (s == segs[j] && p < pen[j]) {
                segs[j] = s;
                pen[j] = p;
                prev[j] = i;
            }
        }
    }
    let mut idx = vec![n - 1];
    while *idx.last().unwrap() != 0 {
        idx.push(prev[*idx.last().unwrap()]);
    }
    idx.reverse();
    idx
}

/// Least-squares line through pts[i..=j]: center of gravity + principal
/// eigenvector (potrace pointslope). Returns (a, b, c) of ax+by+c=0 with
/// (a,b) unit normal, or None if degenerate (all points coincide).
fn fit_line(pts: &[P], i: usize, j: usize) -> Option<[f64; 3]> {
    let k = (j - i + 1) as f64;
    let (mut sx, mut sy, mut sxx, mut sxy, mut syy) = (0.0, 0.0, 0.0, 0.0, 0.0);
    for p in &pts[i..=j] {
        sx += p[0]; sy += p[1];
        sxx += p[0] * p[0]; sxy += p[0] * p[1]; syy += p[1] * p[1];
    }
    let mx = sx / k;
    let my = sy / k;
    let a = sxx / k - mx * mx;
    let b = sxy / k - mx * my;
    let c = syy / k - my * my;
    let lambda2 = (a + c + ((a - c) * (a - c) + 4.0 * b * b).sqrt()) / 2.0;
    let (ar, cr) = (a - lambda2, c - lambda2);
    let (dx, dy); // line DIRECTION
    if ar.abs() >= cr.abs() {
        let l = (ar * ar + b * b).sqrt();
        if l < 1e-12 { return None; }
        dx = -b / l; dy = ar / l;
    } else {
        let l = (cr * cr + b * b).sqrt();
        if l < 1e-12 { return None; }
        dx = -cr / l; dy = b / l;
    }
    let (nx, ny) = (dy, -dx); // unit normal
    Some([nx, ny, -(nx * mx + ny * my)])
}

#[inline]
fn qf_eval(q: &[[f64; 3]; 3], x: f64, y: f64) -> f64 {
    q[0][0] * x * x + 2.0 * q[0][1] * x * y + q[1][1] * y * y
        + 2.0 * q[0][2] * x + 2.0 * q[1][2] * y + q[2][2]
}

/// Move each interior polygon vertex to the point in the +-0.5 box around it
/// minimizing summed squared distance to the two adjacent runs' LS lines
/// (potrace adjust_vertices). Endpoints stay pinned (junctions).
fn adjust_vertices(pts: &[P], idx: &[usize]) -> Vec<P> {
    let m = idx.len();
    let mut out: Vec<P> = idx.iter().map(|&i| pts[i]).collect();
    if m < 3 { return out; }
    // per-segment quadratic forms
    let mut qs: Vec<[[f64; 3]; 3]> = Vec::with_capacity(m - 1);
    for w in idx.windows(2) {
        let mut q = [[0.0f64; 3]; 3];
        if let Some(v) = fit_line(pts, w[0], w[1]) {
            for l in 0..3 {
                for k in 0..3 {
                    q[l][k] = v[l] * v[k];
                }
            }
        }
        qs.push(q);
    }
    for t in 1..m - 1 {
        let mut q = [[0.0f64; 3]; 3];
        for l in 0..3 {
            for k in 0..3 {
                q[l][k] = qs[t - 1][l][k] + qs[t][l][k];
            }
        }
        let v0 = pts[idx[t]];
        let (x0, y0) = (v0[0], v0[1]);
        let mut best = (qf_eval(&q, x0, y0), [x0, y0]);
        let consider = |x: f64, y: f64, best: &mut (f64, P)| {
            let xc = x.clamp(x0 - 0.5, x0 + 0.5);
            let yc = y.clamp(y0 - 0.5, y0 + 0.5);
            let e = qf_eval(&q, xc, yc);
            if e < best.0 { *best = (e, [xc, yc]); }
        };
        // unconstrained minimum
        let det = q[0][0] * q[1][1] - q[0][1] * q[0][1];
        if det.abs() > 1e-12 {
            let wx = (q[0][1] * q[1][2] - q[1][1] * q[0][2]) / det;
            let wy = (q[0][1] * q[0][2] - q[0][0] * q[1][2]) / det;
            if (wx - x0).abs() <= 0.5 && (wy - y0).abs() <= 0.5 {
                out[t] = [wx, wy];
                continue;
            }
            consider(wx, wy, &mut best);
        }
        // box-edge minima (convex quadratic: box min lies on the boundary
        // when the unconstrained min is outside)
        for &x in &[x0 - 0.5, x0 + 0.5] {
            let y = if q[1][1].abs() > 1e-12 { -(q[0][1] * x + q[1][2]) / q[1][1] } else { y0 };
            consider(x, y, &mut best);
            consider(x, y0 - 0.5, &mut best);
            consider(x, y0 + 0.5, &mut best);
        }
        for &y in &[y0 - 0.5, y0 + 0.5] {
            let x = if q[0][0].abs() > 1e-12 { -(q[0][1] * y + q[0][2]) / q[0][0] } else { x0 };
            consider(x, y, &mut best);
        }
        out[t] = best.1;
    }
    out
}

/// Potrace corner measure at vertex b between neighbors a and c:
/// alpha = 4*gamma/3 via dpara/ddenom (potrace smooth()).
fn potrace_alpha(a: P, b: P, c: P) -> f64 {
    let denom = (c[0] - a[0]).abs() + (c[1] - a[1]).abs(); // ddenom (L1)
    if denom < 1e-12 { return 4.0 / 3.0; }
    let dpara = xprod(sub(b, a), sub(c, a));
    let dd = (dpara / denom).abs();
    let alpha = if dd > 1.0 { 1.0 - 1.0 / dd } else { 0.0 };
    alpha / 0.75
}

#[inline]
fn lerp(a: P, b: P, t: f64) -> P { [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])] }

#[inline]
fn line_cubic(a: P, b: P) -> [P; 4] {
    let d = scale(sub(b, a), 1.0 / 3.0);
    [a, add(a, d), sub(b, d), b]
}

// -------------------------------------------- curve optimization (potrace §2.4)

#[inline]
fn dpara3(p0: P, p1: P, p2: P) -> f64 { xprod(sub(p1, p0), sub(p2, p0)) }
#[inline]
fn iprod3(p0: P, p1: P, p2: P) -> f64 { dot(sub(p1, p0), sub(p2, p0)) }
#[inline]
fn cprod4(p0: P, p1: P, q0: P, q1: P) -> f64 { xprod(sub(p1, p0), sub(q1, q0)) }
#[inline]
fn iprod4(p0: P, p1: P, q0: P, q1: P) -> f64 { dot(sub(p1, p0), sub(q1, q0)) }
#[inline]
fn sgn(x: f64) -> i32 { if x > 0.0 { 1 } else if x < 0.0 { -1 } else { 0 } }

/// t in [0,1] where the cubic's tangent is parallel to q1-q0, or -1.0.
fn bez_tangent_t(c: &[P; 4], q0: P, q1: P) -> f64 {
    let a = cprod4(c[0], c[1], q0, q1);
    let b = cprod4(c[1], c[2], q0, q1);
    let cc = cprod4(c[2], c[3], q0, q1);
    let qa = a - 2.0 * b + cc;
    let qb = -2.0 * a + 2.0 * b;
    let qc = a;
    let d = qb * qb - 4.0 * qa * qc;
    if qa.abs() < 1e-12 || d < 0.0 {
        // linear fallback (potrace returns -1 when a == 0)
        if qa.abs() < 1e-12 && qb.abs() > 1e-12 {
            let r = -qc / qb;
            if (0.0..=1.0).contains(&r) { return r; }
        }
        return -1.0;
    }
    let s = d.sqrt();
    let r1 = (-qb + s) / (2.0 * qa);
    let r2 = (-qb - s) / (2.0 * qa);
    if (0.0..=1.0).contains(&r1) { r1 } else if (0.0..=1.0).contains(&r2) { r2 } else { -1.0 }
}

/// One emitted unit of the smoothed polygon: rounds polygon vertex `v`,
/// spans anchors s -> e. Corners emit two lines through v; smooth pieces one
/// cubic with control points cc1/cc2 on the polygon edges.
struct Piece {
    s: P,
    e: P,
    v: P,
    alpha: f64, // clamped [0.55, 1] for smooth pieces
    corner: bool,
    cc1: P,
    cc2: P,
}

impl Piece {
    fn emit(&self, out: &mut Vec<[P; 4]>) {
        if self.corner {
            if norm(sub(self.v, self.s)) > 1e-9 { out.push(line_cubic(self.s, self.v)); }
            if norm(sub(self.e, self.v)) > 1e-9 { out.push(line_cubic(self.v, self.e)); }
        } else {
            out.push([self.s, self.cc1, self.cc2, self.e]);
        }
    }
}

/// Potrace opti_penalty: try to replace pieces i+1..j (all smooth, convexity-
/// consistent, total bend < 179 deg) by ONE cubic from anchor[i] to anchor[j]
/// that preserves enclosed area, checking tangency within opttolerance.
/// a = adjusted polygon vertices, anchors[k] = end anchor of piece k.
#[allow(clippy::too_many_arguments)]
fn opti_penalty(
    a: &[P], anchors: &[P], pieces: &[Piece], conv: &[i32], areac: &[f64],
    aref: P, i: usize, j: usize, opttol: f64,
) -> Option<(f64, [P; 4])> {
    const COS179: f64 = -0.999_847_695_156_391_3;
    // all merged pieces must be smooth
    for p in &pieces[i + 1..=j] {
        if p.corner { return None; }
    }
    let conv0 = conv[i + 1];
    if conv0 == 0 { return None; }
    let d0 = norm(sub(a[i + 1], a[i]));
    if d0 < 1e-12 { return None; }
    for k in (i + 1)..j {
        if conv[k + 1] != conv0 { return None; }
        if sgn(cprod4(a[i], a[i + 1], a[k], a[k + 1])) != conv0 { return None; }
        if iprod4(a[i], a[i + 1], a[k], a[k + 1])
            < d0 * norm(sub(a[k + 1], a[k])) * COS179 { return None; }
    }
    let p0 = anchors[i];
    let p1 = a[i + 1];
    let p2 = a[j];
    let p3 = anchors[j];

    // area between the original piecewise curve p0..p3 and the chord p3->p0
    let area = areac[j] - areac[i] - dpara3(aref, anchors[i], anchors[j]) / 2.0;

    // intersection o of lines p0p1 and p3p2; alpha from area preservation
    let a1 = dpara3(p0, p1, p2);
    let a2 = dpara3(p0, p1, p3);
    let a3 = dpara3(p0, p2, p3);
    let a4 = a1 + a3 - a2;
    if (a2 - a1).abs() < 1e-12 || (a3 - a4).abs() < 1e-12 { return None; }
    let t = a3 / (a3 - a4);
    let s = a2 / (a2 - a1);
    let big_a = a2 * t / 2.0;
    if big_a.abs() < 1e-12 { return None; }
    let r = area / big_a;
    let disc = 4.0 - r / 0.3;
    if disc < 0.0 { return None; }
    let alpha = 2.0 - disc.sqrt();
    if !(0.0..=1.34).contains(&alpha) { return None; }

    let cand = [p0, lerp(p0, p1, t * alpha), lerp(p3, p2, s * alpha), p3];
    let mut pen = 0.0;

    // tangency to interior polygon edges
    for k in (i + 1)..j {
        let tt = bez_tangent_t(&cand, a[k], a[k + 1]);
        if tt < -0.5 { return None; }
        let pt = bezier_point(&cand, tt);
        let d = norm(sub(a[k + 1], a[k]));
        if d < 1e-12 { return None; }
        let d1 = dpara3(a[k], a[k + 1], pt) / d;
        if d1.abs() > opttol { return None; }
        if iprod3(a[k], a[k + 1], pt) < 0.0 || iprod3(a[k + 1], a[k], pt) < 0.0 {
            return None;
        }
        pen += d1 * d1;
    }
    // stay on the correct side of each replaced piece's anchor chord
    for k in i..j {
        let tt = bez_tangent_t(&cand, anchors[k], anchors[k + 1]);
        if tt < -0.5 { return None; }
        let pt = bezier_point(&cand, tt);
        let d = norm(sub(anchors[k + 1], anchors[k]));
        if d < 1e-12 { return None; }
        let mut d1 = dpara3(anchors[k], anchors[k + 1], pt) / d;
        let mut d2 = dpara3(anchors[k], anchors[k + 1], a[k + 1]) / d;
        d2 *= 0.75 * pieces[k + 1].alpha;
        if d2 < 0.0 {
            d1 = -d1;
            d2 = -d2;
        }
        if d1 < d2 - opttol { return None; }
        if d1 < d2 { pen += (d1 - d2) * (d1 - d2); }
    }
    Some((pen, cand))
}

/// Potrace-style PARSIMONY fit of an OPEN polyline (crack-lattice points).
/// Pipeline (Potrace §2.2-2.4 adapted to open chains):
///   minimal-segment polygon (DP) -> sub-pixel vertex adjustment -> tangent-
///   constrained cubics through edge midpoints -> area-preserving curve merge.
/// Endpoints exact (junction-safe). alpha >= alphamax => corner (two line
/// segments through the vertex). opttolerance <= 0 disables the merge pass.
/// Input [x0,y0,x1,y1,...]; output flat cubics [p0x,p0y,c1x,c1y,c2x,c2y,
/// p3x,p3y] * n (same convention as fit_open).
#[pyfunction]
#[pyo3(signature = (flat, alphamax=1.0, opttolerance=0.2))]
fn fit_open_parsimony(flat: Vec<f64>, alphamax: f64, opttolerance: f64) -> Vec<f64> {
    let raw: Vec<P> = (0..flat.len() / 2).map(|i| [flat[2 * i], flat[2 * i + 1]]).collect();
    // dedupe consecutive duplicates (defensive: callers may repeat points)
    let mut pts: Vec<P> = Vec::with_capacity(raw.len());
    for p in raw {
        if pts.last().map_or(true, |q| norm(sub(p, *q)) > 1e-9) {
            pts.push(p);
        }
    }
    let n = pts.len();
    if n < 2 { return vec![]; }
    let flatten = |curves: &[[P; 4]]| -> Vec<f64> {
        curves.iter().flat_map(|c| c.iter().flat_map(|p| p.to_vec())).collect()
    };
    if n == 2 {
        return flatten(&[line_cubic(pts[0], pts[1])]);
    }
    let idx = best_polygon_open(&pts);
    let a = adjust_vertices(&pts, &idx);
    let m = a.len() - 1; // number of polygon segments
    if m == 1 {
        return flatten(&[line_cubic(a[0], a[1])]);
    }
    // pieces j=1..m-1: piece j rounds vertex a[j] and spans anchors
    // anchor[j-1] -> anchor[j]; chain endpoints replace the outermost
    // midpoints so junctions stay exact.
    let mut anchors: Vec<P> = Vec::with_capacity(m);
    anchors.push(a[0]);
    for k in 1..m - 1 {
        anchors.push(lerp(a[k], a[k + 1], 0.5));
    }
    anchors.push(a[m]);
    let mut pieces: Vec<Piece> = Vec::with_capacity(m); // index 1..m-1 used
    pieces.push(Piece { s: a[0], e: a[0], v: a[0], alpha: 0.0, corner: true, cc1: a[0], cc2: a[0] });
    for j in 1..m {
        let s = anchors[j - 1];
        let e = anchors[j];
        let alpha = potrace_alpha(a[j - 1], a[j], a[j + 1]);
        if alpha >= alphamax {
            pieces.push(Piece { s, e, v: a[j], alpha: 0.0, corner: true, cc1: a[j], cc2: a[j] });
        } else {
            let al = alpha.clamp(0.55, 1.0);
            let t = 0.5 + 0.5 * al;
            pieces.push(Piece {
                s, e, v: a[j], alpha: al, corner: false,
                cc1: lerp(a[j - 1], a[j], t), cc2: lerp(a[j + 1], a[j], t),
            });
        }
    }
    let np = m - 1; // pieces are 1..=np, anchors 0..=np

    let mut curves: Vec<[P; 4]> = Vec::new();
    if opttolerance <= 0.0 || np < 2 {
        for p in &pieces[1..] { p.emit(&mut curves); }
        return flatten(&curves);
    }

    // convexity sign per piece (0 = corner: never merged)
    let mut conv = vec![0i32; np + 1];
    for j in 1..=np {
        if !pieces[j].corner {
            conv[j] = sgn(dpara3(a[j - 1], a[j], a[j + 1]));
        }
    }
    // prefix signed areas of the piecewise curve relative to aref
    let aref = a[0];
    let mut areac = vec![0.0f64; np + 1];
    for j in 1..=np {
        let mut inc = 0.0;
        if !pieces[j].corner {
            let al = pieces[j].alpha;
            inc += 0.3 * al * (4.0 - al) * dpara3(anchors[j - 1], a[j], anchors[j]) / 2.0;
            inc += dpara3(aref, anchors[j - 1], anchors[j]) / 2.0;
        }
        areac[j] = areac[j - 1] + inc;
    }

    // DP over anchors: fewest emitted segments, then min penalty
    const BIG: usize = usize::MAX;
    let mut segs = vec![BIG; np + 1];
    let mut pen = vec![f64::INFINITY; np + 1];
    let mut prev: Vec<usize> = (0..=np).collect();
    let mut merged: Vec<Option<[P; 4]>> = vec![None; np + 1];
    segs[0] = 0;
    pen[0] = 0.0;
    for j in 1..=np {
        // identity step: emit piece j as-is (corner counts as one unit)
        let s0 = segs[j - 1] + 1;
        if s0 < segs[j] {
            segs[j] = s0;
            pen[j] = pen[j - 1];
            prev[j] = j - 1;
            merged[j] = None;
        }
        for i in 0..j.saturating_sub(1) {
            if segs[i] == BIG { continue; }
            if let Some((p, cand)) =
                opti_penalty(&a, &anchors, &pieces, &conv, &areac, aref, i, j, opttolerance)
            {
                let s = segs[i] + 1;
                let pp = pen[i] + p;
                if s < segs[j] || (s == segs[j] && pp < pen[j]) {
                    segs[j] = s;
                    pen[j] = pp;
                    prev[j] = i;
                    merged[j] = Some(cand);
                }
            }
        }
    }
    // reconstruct
    let mut cuts = vec![np];
    while *cuts.last().unwrap() != 0 {
        cuts.push(prev[*cuts.last().unwrap()]);
    }
    cuts.reverse();
    for w in cuts.windows(2) {
        let j = w[1];
        if let Some(c) = merged[j] {
            curves.push(c);
        } else {
            pieces[j].emit(&mut curves);
        }
    }
    flatten(&curves)
}

#[pymodule]
fn svgcore(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(count_points, m)?)?;
    m.add_function(wrap_pyfunction!(simplify_path, m)?)?;
    m.add_function(wrap_pyfunction!(fit_open, m)?)?;
    m.add_function(wrap_pyfunction!(fit_open_parsimony, m)?)?;
    Ok(())
}
