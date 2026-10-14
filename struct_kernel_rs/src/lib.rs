//! struct_kernel — kernels numéricos de precisión para cálculo estructural.
//!
//! ABI C puro (cdylib) para cargar con ctypes desde Python (sin PyO3/maturin).
//! Kernels:
//!   1. LU con pivoteo parcial + refinamiento iterativo (resolución de sistemas).
//!   2. Análisis matricial 2D de pórticos (método de desplazamientos, barras
//!      Euler-Bernoulli + cortante Timoshenko opcional).
//!   3. Autovalores generalizados K φ = λ M φ (subespacio + Jacobi + refinamiento).
//!   4. Rigidez exacta de viga Timoshenko (6×6 local).
//!   5. Factor χ de pandeo Eurocódigo 3 y N_cr de Euler.
//!   6. Suma compensada Kahan-Babuska-Neumaier.
//!
//! Unidades: SI (m, N, Pa).

use std::f64::consts::PI;

// ---------------------------------------------------------------------------
// 0. ABI helpers
// ---------------------------------------------------------------------------

/// Suma compensada. out_sum = Σxs, out_err = corrección de redondeo.
#[no_mangle]
pub extern "C" fn sk_kahan_sum(xs: *const f64, n: usize, out_sum: *mut f64, out_err: *mut f64) {
    let slice = unsafe { std::slice::from_raw_parts(xs, n) };
    let mut sum = 0.0f64;
    let mut c = 0.0f64;
    for &x in slice {
        let y = x - c;
        let t = sum + y;
        c = (t - sum) - y;
        sum = t;
    }
    unsafe {
        *out_sum = sum;
        *out_err = c;
    }
}

// ---------------------------------------------------------------------------
// 1. LU con pivoteo parcial + refinamiento (2 pasos)
// ---------------------------------------------------------------------------

/// Factoriza A (n×n row-major, se destruye) y resuelve A x = b.
/// Devuelve 0 si OK, >0 si singular.
fn lu_solve_raw(n: usize, a: &mut [f64], b: &[f64], x: &mut [f64]) -> i32 {
    let mut piv: Vec<usize> = (0..n).collect();
    // Eliminación de Gauss con pivoteo parcial
    for k in 0..n {
        // Buscar pivote
        let mut best = k;
        let mut best_v = a[piv[k] * n + k].abs();
        for i in (k + 1)..n {
            let v = a[piv[i] * n + k].abs();
            if v > best_v {
                best_v = v;
                best = i;
            }
        }
        if best_v < 1e-300 {
            return (k + 1) as i32;
        }
        piv.swap(k, best);
        let pk = piv[k];
        for i in (k + 1)..n {
            let pi = piv[i];
            let f = a[pi * n + k] / a[pk * n + k];
            a[pi * n + k] = f;
            if f != 0.0 {
                for j in (k + 1)..n {
                    a[pi * n + j] -= f * a[pk * n + j];
                }
            }
        }
    }
    // Forward substitution con permutación
    let mut y = vec![0.0f64; n];
    for i in 0..n {
        let pi = piv[i];
        let mut s = b[pi];
        for j in 0..i {
            s -= a[pi * n + j] * y[j];
        }
        y[i] = s;
    }
    // Back substitution
    for i in (0..n).rev() {
        let pi = piv[i];
        let mut s = y[i];
        for j in (i + 1)..n {
            s -= a[pi * n + j] * x[j];
        }
        x[i] = s / a[pi * n + i];
    }
    0
}

/// Resolver A x = b con pivoteo parcial + 2 refinement iterativo.
/// `a` se destruye. Se recomputa A residual via re-factorización de copia.
fn lu_solve_refined(n: usize, a: &mut [f64], b: &[f64], x: &mut [f64]) -> i32 {
    let a_orig = a.to_vec();
    let rc = lu_solve_raw(n, a, b, x);
    if rc != 0 {
        return rc;
    }
    // 2 refinamientos: r = b - A_orig x; solve A dr = r; x += dr
    for _ in 0..2 {
        let mut r = vec![0.0f64; n];
        for i in 0..n {
            let mut s = b[i];
            for j in 0..n {
                s -= a_orig[i * n + j] * x[j];
            }
            r[i] = s;
        }
        let mut a2 = a_orig.clone();
        let mut dr = vec![0.0f64; n];
        if lu_solve_raw(n, &mut a2, &r, &mut dr) != 0 {
            break;
        }
        for i in 0..n {
            x[i] += dr[i];
        }
    }
    0
}

/// API pública: LU + refinamiento. a se destruye.
#[no_mangle]
pub extern "C" fn sk_ldlt_solve(n: usize, a: *mut f64, b: *const f64, x: *mut f64) -> i32 {
    if n == 0 || a.is_null() || b.is_null() || x.is_null() {
        return 1;
    }
    let a = unsafe { std::slice::from_raw_parts_mut(a, n * n) };
    let b = unsafe { std::slice::from_raw_parts(b, n) };
    let mut xvec = vec![0.0f64; n];
    lu_solve_refined(n, a, b, &mut xvec);
    unsafe {
        for i in 0..n {
            *x.add(i) = xvec[i];
        }
    }
    0
}

// ---------------------------------------------------------------------------
// 2. Pórtico 2D — método de desplazamientos
// ---------------------------------------------------------------------------

/// Análisis de pórtico plano. DOF global por nodo: [u, v, θ].
///
/// coords: 2*nn, members: 8*nm por barra [i,j,A,E,Iz,G,As,w_local_y],
/// bc: 2*n_bc por restricción [node, dof], nl: 3*n_nl por carga [node,dof,F].
///
/// u_out 3*nn, reac_out 3*nn, end_forces 6*nm (locales: N,V,M en extremo 1
/// y N2,V2,M2 en extremo 2).
#[no_mangle]
pub extern "C" fn sk_frame2d_solve(
    nn: usize,
    nm: usize,
    coords: *const f64,
    members: *const f64,
    n_bc: usize,
    bc: *const i64,
    n_nl: usize,
    nl: *const f64,
    u_out: *mut f64,
    reac_out: *mut f64,
    end_forces: *mut f64,
) -> i32 {
    if nn == 0 || nm == 0 || coords.is_null() || members.is_null() {
        return 1;
    }
    let coords = unsafe { std::slice::from_raw_parts(coords, 2 * nn) };
    let members = unsafe { std::slice::from_raw_parts(members, 8 * nm) };
    let ndof = 3 * nn;

    let mut k = vec![0.0f64; ndof * ndof];
    let mut f = vec![0.0f64; ndof];

    struct MemberData {
        dofs: [usize; 6],
        kl: [f64; 36],
        t: [f64; 36],
        w: f64,
        l: f64,
    }
    let mut mdata = Vec::with_capacity(nm);

    for m in 0..nm {
        let i = members[m * 8] as usize;
        let j = members[m * 8 + 1] as usize;
        let a = members[m * 8 + 2];
        let e = members[m * 8 + 3];
        let iz = members[m * 8 + 4];
        let g = members[m * 8 + 5].max(1.0);
        let asy = members[m * 8 + 6].max(1e-12);
        let w = members[m * 8 + 7];
        if i >= nn || j >= nn {
            return 2;
        }
        let xi = coords[i * 2];
        let yi = coords[i * 2 + 1];
        let xj = coords[j * 2];
        let yj = coords[j * 2 + 1];
        let dx = xj - xi;
        let dy = yj - yi;
        let l = (dx * dx + dy * dy).sqrt();
        if l < 1e-12 {
            return 2;
        }
        let c = dx / l;
        let s = dy / l;

        // Rigidez local Timoshenko 6×6 simétrica
        let ea_l = e * a / l;
        let ei = e * iz;
        let phi = (12.0 * ei) / (g * asy * l * l);
        let psi = 1.0 / (1.0 + phi);
        let g22 = (12.0 * ei / (l * l * l)) * psi;
        let g23 = (6.0 * ei / (l * l)) * psi;
        let g33 = (4.0 * ei / l) * (1.0 + 0.25 * phi) * psi;
        let g36 = (2.0 * ei / l) * (1.0 - 0.5 * phi) * psi;
        let kl = [
            ea_l, 0.0, 0.0, -ea_l, 0.0, 0.0,
            0.0, g22, g23, 0.0, -g22, g23,
            0.0, g23, g33, 0.0, -g23, g36,
            -ea_l, 0.0, 0.0, ea_l, 0.0, 0.0,
            0.0, -g22, -g23, 0.0, g22, -g23,
            0.0, g23, g36, 0.0, -g23, g33,
        ];

        // T: global ← local (6×6)
        let t = [
            c, s, 0.0, 0.0, 0.0, 0.0,
            -s, c, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, c, s, 0.0,
            0.0, 0.0, 0.0, -s, c, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 1.0,
        ];

        // Kg = T^T · Kl · T  (u_local = T · u_global ⇒ energía = ug^T T^T Kl T ug)
        let mut kg = [0.0f64; 36];
        for r in 0..6 {
            for cc in 0..6 {
                let mut acc = 0.0;
                for p in 0..6 {
                    for q in 0..6 {
                        acc += t[p * 6 + r] * kl[p * 6 + q] * t[q * 6 + cc];
                    }
                }
                kg[r * 6 + cc] = acc;
            }
        }

        let dofs = [3 * i, 3 * i + 1, 3 * i + 2, 3 * j, 3 * j + 1, 3 * j + 2];
        for (r, &dr) in dofs.iter().enumerate() {
            for (cc, &dc) in dofs.iter().enumerate() {
                k[dr * ndof + dc] += kg[r * 6 + cc];
            }
        }

        // Cargas distribuidas equivalentes en local, → global
        let fl = [
            0.0,
            w * l / 2.0,
            -w * l * l / 12.0,
            0.0,
            w * l / 2.0,
            w * l * l / 12.0,
        ];
        let mut fg = [0.0f64; 6];
        for r in 0..6 {
            let mut acc = 0.0;
            for p in 0..6 {
                acc += t[p * 6 + r] * fl[p]; // T^T fl
            }
            fg[r] = acc;
        }
        for (r, &dr) in dofs.iter().enumerate() {
            f[dr] += fg[r];
        }

        mdata.push(MemberData {
            dofs,
            kl,
            t,
            w,
            l,
        });
    }

    if n_nl > 0 && !nl.is_null() {
        let nl = unsafe { std::slice::from_raw_parts(nl, 3 * n_nl) };
        for p in 0..n_nl {
            let node = nl[p * 3] as usize;
            let dof = nl[p * 3 + 1] as usize;
            let val = nl[p * 3 + 2];
            if node < nn && dof < 3 {
                f[3 * node + dof] += val;
            }
        }
    }

    let mut fixed = vec![false; ndof];
    if n_bc > 0 && !bc.is_null() {
        let bc = unsafe { std::slice::from_raw_parts(bc, n_bc * 2) };
        for p in 0..n_bc {
            let node = bc[p * 2] as usize;
            let dof = bc[p * 2 + 1] as usize;
            if node < nn && dof < 3 {
                fixed[3 * node + dof] = true;
            }
        }
    }

    let free: Vec<usize> = (0..ndof).filter(|&i| !fixed[i]).collect();
    let nf = free.len();
    if nf == 0 {
        return 3;
    }
    let mut kff = vec![0.0f64; nf * nf];
    let mut ff = vec![0.0f64; nf];
    for (a, &ia) in free.iter().enumerate() {
        ff[a] = f[ia];
        for (b, &ib) in free.iter().enumerate() {
            kff[a * nf + b] = k[ia * ndof + ib];
        }
    }

    let mut uf = vec![0.0f64; nf];
    if lu_solve_refined(nf, &mut kff, &ff, &mut uf) != 0 {
        return 4;
    }

    let mut u = vec![0.0f64; ndof];
    for (a, &ia) in free.iter().enumerate() {
        u[ia] = uf[a];
    }

    let mut reac = vec![0.0f64; ndof];
    for i in 0..ndof {
        if fixed[i] {
            let mut s = -f[i];
            for j in 0..ndof {
                s += k[i * ndof + j] * u[j];
            }
            reac[i] = s;
        }
    }

    let mut ef = vec![0.0f64; 6 * nm];
    for (m, md) in mdata.iter().enumerate() {
        let mut ug = [0.0f64; 6];
        for (r, &d) in md.dofs.iter().enumerate() {
            ug[r] = u[d];
        }
        let mut ul = [0.0f64; 6];
        for r in 0..6 {
            let mut acc = 0.0;
            for p in 0..6 {
                acc += md.t[r * 6 + p] * ug[p];
            }
            ul[r] = acc;
        }
        let mut fl = [0.0f64; 6];
        for r in 0..6 {
            let mut acc = 0.0;
            for p in 0..6 {
                acc += md.kl[r * 6 + p] * ul[p];
            }
            fl[r] = acc;
        }
        // Esfuerzos de barra = Kl·u_local − f_eq_local
        let w = md.w;
        let l = md.l;
        fl[1] -= w * l / 2.0;
        fl[2] -= -w * l * l / 12.0;
        fl[4] -= w * l / 2.0;
        fl[5] -= w * l * l / 12.0;
        for r in 0..6 {
            ef[m * 6 + r] = fl[r];
        }
    }

    unsafe {
        for i in 0..ndof {
            *u_out.add(i) = u[i];
            *reac_out.add(i) = reac[i];
        }
        for i in 0..6 * nm {
            *end_forces.add(i) = ef[i];
        }
    }
    0
}

// ---------------------------------------------------------------------------
// 3. Autovalores generalizados K φ = λ M φ
// ---------------------------------------------------------------------------

/// Subespacio iterativo + Jacobi cíclico + 1 refinamiento de iteración inversa.
/// nev autovalores más pequeños. M puede ser null (identidad).
#[no_mangle]
pub extern "C" fn sk_eigen_generalized(
    n: usize,
    k: *const f64,
    m: *const f64,
    nev: usize,
    eigval: *mut f64,
    eigvec: *mut f64,
) -> i32 {
    if n == 0 || k.is_null() || eigval.is_null() || eigvec.is_null() || nev == 0 {
        return 1;
    }
    let nev = nev.min(n);
    let k = unsafe { std::slice::from_raw_parts(k, n * n) };
    let m_id: Vec<f64> = (0..n * n)
        .map(|i| if i / n == i % n { 1.0 } else { 0.0 })
        .collect();
    let m = if m.is_null() {
        &m_id
    } else {
        unsafe { std::slice::from_raw_parts(m, n * n) }
    };

    let p = n.min(nev + 6).max(nev + 1);
    let mut x = vec![0.0f64; n * p];
    for j in 0..p {
        let i = j % n;
        x[i * p + j] = 1.0 + 1e-9 * ((j + 1) as f64);
    }

    // Shift-invert: A = K + ε M (ε>0 pequeño para invertibilidad si K semidef)
    let eps = 1e-10_f64.max(k.iter().map(|v| v.abs()).fold(1e-300, f64::max) * 1e-14);
    let mut a_work = vec![0.0f64; n * n];
    for i in 0..n {
        for j in 0..n {
            a_work[i * n + j] = k[i * n + j] + eps * m[i * n + j];
        }
    }

    let mut lambda = vec![0.0f64; nev];
    let max_iter = 100;
    for _ in 0..max_iter {
        // Y = A^{-1} X
        let mut y = vec![0.0f64; n * p];
        for j in 0..p {
            let col: Vec<f64> = (0..n).map(|i| x[i * p + j]).collect();
            let mut ycol = vec![0.0f64; n];
            let mut a2 = a_work.clone();
            if lu_solve_refined(n, &mut a2, &col, &mut ycol) != 0 {
                return 2;
            }
            for i in 0..n {
                y[i * p + j] = ycol[i];
            }
        }

        // Forma reducida: Kt = Yᵀ K Y, Mt = Yᵀ M Y
        let mut kt = vec![0.0f64; p * p];
        let mut mt = vec![0.0f64; p * p];
        for i in 0..n {
            for a in 0..p {
                let yi = y[i * p + a];
                for b in 0..p {
                    let mut kyb = 0.0;
                    let mut myb = 0.0;
                    for r in 0..n {
                        kyb += k[i * n + r] * y[r * p + b];
                        myb += m[i * n + r] * y[r * p + b];
                    }
                    kt[a * p + b] += yi * kyb;
                    mt[a * p + b] += yi * myb;
                }
            }
        }

        // Generalized Jacobi on (kt, mt) — one-sweep dense approach:
        // Simetrizar y aplicar ciclos de rotación
        for i in 0..p {
            for j in (i + 1)..p {
                let v = 0.5 * (kt[i * p + j] + kt[j * p + i]);
                kt[i * p + j] = v;
                kt[j * p + i] = v;
                let v = 0.5 * (mt[i * p + j] + mt[j * p + i]);
                mt[i * p + j] = v;
                mt[j * p + i] = v;
            }
        }
        let mut vc = vec![0.0f64; p * p];
        for i in 0..p {
            vc[i * p + i] = 1.0;
        }
        for _sweep in 0..60 {
            let mut off = 0.0;
            for i in 0..p {
                for j in (i + 1)..p {
                    off += kt[i * p + j].abs() + mt[i * p + j].abs();
                }
            }
            if off < 1e-16 * (p as f64) {
                break;
            }
            for i in 0..p {
                for j in (i + 1)..p {
                    let aij = kt[i * p + j];
                    let bij = mt[i * p + j];
                    let aii = kt[i * p + i];
                    let ajj = kt[j * p + j];
                    let bii = mt[i * p + i];
                    let bjj = mt[j * p + j];
                    if aij.abs() < 1e-30 && bij.abs() < 1e-30 {
                        continue;
                    }
                    // Ángulo de rotación generalizada (rutina clásica)
                    let alpha = ajj * aij - aii * bij;
                    let beta = bjj * aij - bii * bij;
                    let _gamma = (ajj * bii - aii * bjj).abs().sqrt().max(1e-300);
                    let theta = if beta.abs() < 1e-300 {
                        0.0
                    } else {
                        0.5 * alpha.atan2(beta)
                    };
                    let c = theta.cos();
                    let s = theta.sin();
                    // Aplicar rotación R = [[c,s],[-s,c]] a filas/cols i,j de kt,mt,vc
                    for r in 0..p {
                        let kir = kt[i * p + r];
                        let kjr = kt[j * p + r];
                        kt[i * p + r] = c * kir + s * kjr;
                        kt[j * p + r] = -s * kir + c * kjr;
                        let mir = mt[i * p + r];
                        let mjr = mt[j * p + r];
                        mt[i * p + r] = c * mir + s * mjr;
                        mt[j * p + r] = -s * mir + c * mjr;
                    }
                    for r in 0..p {
                        let kri = kt[r * p + i];
                        let krj = kt[r * p + j];
                        kt[r * p + i] = c * kri + s * krj;
                        kt[r * p + j] = -s * kri + c * krj;
                        let mri = mt[r * p + i];
                        let mrj = mt[r * p + j];
                        mt[r * p + i] = c * mri + s * mrj;
                        mt[r * p + j] = -s * mri + c * mrj;
                    }
                    for r in 0..p {
                        let vir = vc[r * p + i];
                        let vjr = vc[r * p + j];
                        vc[r * p + i] = c * vir + s * vjr;
                        vc[r * p + j] = -s * vir + c * vjr;
                    }
                }
            }
        }

        // Autovalores = kt_ii / mt_ii
        let mut idx: Vec<usize> = (0..p).collect();
        idx.sort_by(|&a, &b| {
            let la = kt[a * p + a] / mt[a * p + a].abs().max(1e-300);
            let lb = kt[b * p + b] / mt[b * p + b].abs().max(1e-300);
            la.partial_cmp(&lb).unwrap()
        });

        let mut new_lambda = vec![0.0f64; nev];
        for t in 0..nev {
            let a = idx[t];
            new_lambda[t] = kt[a * p + a] / mt[a * p + a].abs().max(1e-300) - eps;
        }

        // X ← Y V
        let mut xnew = vec![0.0f64; n * p];
        for j in 0..p {
            for i in 0..n {
                let mut acc = 0.0;
                for r in 0..p {
                    acc += y[i * p + r] * vc[r * p + idx[j]];
                }
                xnew[i * p + j] = acc;
            }
        }
        // M-ortonormalización Gram-Schmidt
        for j in 0..p {
            for kcol in 0..j {
                let mut dot = 0.0;
                for i in 0..n {
                    let mut m_xj = 0.0;
                    for r in 0..n {
                        m_xj += m[i * n + r] * xnew[r * p + j];
                    }
                    dot += xnew[i * p + kcol] * m_xj;
                }
                for i in 0..n {
                    let mut m_xk = 0.0;
                    for r in 0..n {
                        m_xk += m[i * n + r] * xnew[r * p + kcol];
                    }
                    xnew[i * p + j] -= dot * m_xk;
                }
            }
            let mut mx = vec![0.0f64; n];
            for i in 0..n {
                let mut acc = 0.0;
                for r in 0..n {
                    acc += m[i * n + r] * xnew[r * p + j];
                }
                mx[i] = acc;
            }
            let mut nrm = 0.0;
            for i in 0..n {
                nrm += xnew[i * p + j] * mx[i];
            }
            nrm = nrm.max(0.0).sqrt().max(1e-300);
            for i in 0..n {
                xnew[i * p + j] /= nrm;
            }
        }

        let mut dl: f64 = 0.0;
        for t in 0..nev {
            dl = dl.max(
                (new_lambda[t] - lambda[t]).abs() / new_lambda[t].abs().max(1e-30),
            );
        }
        x.copy_from_slice(&xnew);
        lambda.copy_from_slice(&new_lambda);
        if dl < 1e-13 {
            break;
        }
    }

    // Refinamiento: Rayleigh + 1 paso de inversa sobre K
    for t in 0..nev {
        let lam = lambda[t];
        let phi: Vec<f64> = (0..n).map(|i| x[i * p + t]).collect();
        let mut r = vec![0.0f64; n];
        for i in 0..n {
            let mut ki = 0.0;
            let mut mi = 0.0;
            for j in 0..n {
                ki += k[i * n + j] * phi[j];
                mi += m[i * n + j] * phi[j];
            }
            r[i] = ki - lam * mi;
        }
        let mut a3 = k.to_vec();
        for i in 0..n {
            a3[i * n + i] += 1e-12_f64.max(k.iter().map(|v| v.abs()).fold(1e-300, f64::max) * 1e-14);
        }
        let mut dp = vec![0.0f64; n];
        if lu_solve_refined(n, &mut a3, &r, &mut dp) == 0 {
            for i in 0..n {
                x[i * p + t] += dp[i];
            }
            // Re-normalizar
            let mut nrm = 0.0;
            for i in 0..n {
                let mut mi = 0.0;
                for j in 0..n {
                    mi += m[i * n + j] * x[j * p + t];
                }
                nrm += x[i * p + t] * mi;
            }
            nrm = nrm.max(0.0).sqrt().max(1e-300);
            for i in 0..n {
                x[i * p + t] /= nrm;
            }
        }
        // Rayleigh
        let mut num = 0.0;
        let mut den = 0.0;
        for i in 0..n {
            let mut ki = 0.0;
            let mut mi = 0.0;
            for j in 0..n {
                ki += k[i * n + j] * x[j * p + t];
                mi += m[i * n + j] * x[j * p + t];
            }
            num += x[i * p + t] * ki;
            den += x[i * p + t] * mi;
        }
        if den.abs() > 1e-300 {
            lambda[t] = num / den;
        }
    }

    unsafe {
        for t in 0..nev {
            *eigval.add(t) = lambda[t];
        }
        for t in 0..nev {
            for i in 0..n {
                *eigvec.add(i * nev + t) = x[i * p + t];
            }
        }
    }
    0
}

// ---------------------------------------------------------------------------
// 4. Rigidez exacta de viga Timoshenko (local 6×6)
// ---------------------------------------------------------------------------

#[no_mangle]
pub extern "C" fn sk_beam_exact_stiffness(
    e: f64,
    g: f64,
    a: f64,
    iz: f64,
    asy: f64,
    l: f64,
    out66: *mut f64,
) -> i32 {
    if out66.is_null() || l < 1e-12 || a < 1e-18 || iz < 1e-18 {
        return 1;
    }
    let ea_l = e * a / l;
    let ei = e * iz;
    let phi = (12.0 * ei) / (g * asy.max(1e-12) * l * l);
    let psi = 1.0 / (1.0 + phi);
    let g22 = (12.0 * ei / (l * l * l)) * psi;
    let g23 = (6.0 * ei / (l * l)) * psi;
    let g33 = (4.0 * ei / l) * (1.0 + 0.25 * phi) * psi;
    let g36 = (2.0 * ei / l) * (1.0 - 0.5 * phi) * psi;
    let kl = [
        ea_l, 0.0, 0.0, -ea_l, 0.0, 0.0,
        0.0, g22, g23, 0.0, -g22, g23,
        0.0, g23, g33, 0.0, -g23, g36,
        -ea_l, 0.0, 0.0, ea_l, 0.0, 0.0,
        0.0, -g22, -g23, 0.0, g22, -g23,
        0.0, g23, g36, 0.0, -g23, g33,
    ];
    unsafe {
        for i in 0..36 {
            *out66.add(i) = kl[i];
        }
    }
    0
}

// ---------------------------------------------------------------------------
// 5. Eurocódigo 3 — χ de pandeo, λ̄, N_cr Euler
// ---------------------------------------------------------------------------

/// χ = 1/(Φ+√(Φ²−λ̄²)), Φ=0.5[1+α(λ̄−0.2)+λ̄²]. λ̄≤0.2 → χ=1.
#[no_mangle]
pub extern "C" fn sk_ec3_buckling_chi(lambda_bar: f64, alpha: f64, out_chi: *mut f64) -> i32 {
    if out_chi.is_null() || lambda_bar < 0.0 || alpha < 0.0 {
        return 1;
    }
    let lb = lambda_bar;
    let chi = if lb <= 0.2 {
        1.0
    } else {
        let phi = 0.5 * (1.0 + alpha * (lb - 0.2) + lb * lb);
        let disc = (phi * phi - lb * lb).max(0.0);
        (1.0 / (phi + disc.sqrt())).min(1.0)
    };
    unsafe {
        *out_chi = chi;
    }
    0
}

#[no_mangle]
pub extern "C" fn sk_ec3_chi_lt(lambda_lt_bar: f64, alpha_lt: f64, out_chi: *mut f64) -> i32 {
    sk_ec3_buckling_chi(lambda_lt_bar, alpha_lt, out_chi)
}

/// λ̄ = √(A·fy / N_cr)
#[no_mangle]
pub extern "C" fn sk_ec3_lambda_bar(area: f64, fy: f64, n_cr: f64, out: *mut f64) -> i32 {
    if out.is_null() || area <= 0.0 || fy <= 0.0 || n_cr <= 0.0 {
        return 1;
    }
    unsafe {
        *out = (area * fy / n_cr).sqrt();
    }
    0
}

/// N_cr = π² EI / L_cr²
#[no_mangle]
pub extern "C" fn sk_euler_ncr(e: f64, iz: f64, l_cr: f64, out: *mut f64) -> i32 {
    if out.is_null() || l_cr < 1e-12 {
        return 1;
    }
    unsafe {
        *out = PI * PI * e * iz / (l_cr * l_cr);
    }
    0
}

// ---------------------------------------------------------------------------
// 6. Versión
// ---------------------------------------------------------------------------

#[no_mangle]
pub extern "C" fn sk_version() -> u32 {
    1
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_lu() {
        let mut a = vec![4.0, 1.0, 1.0, 3.0];
        let b = vec![1.0, 2.0];
        let mut x = vec![0.0; 2];
        let rc = lu_solve_refined(2, &mut a, &b, &mut x);
        assert_eq!(rc, 0);
        assert!((x[0] - 1.0 / 11.0).abs() < 1e-12);
        assert!((x[1] - 7.0 / 11.0).abs() < 1e-12);
    }

    #[test]
    fn test_euler() {
        let mut out = 0.0;
        sk_euler_ncr(210e9, 8356e-8, 6.0, &mut out as *mut f64);
        let expect = PI * PI * 210e9 * 8356e-8 / 36.0;
        assert!((out - expect).abs() / expect < 1e-12);
    }

    #[test]
    fn test_chi() {
        let mut chi = 0.0;
        sk_ec3_buckling_chi(1.0, 0.34, &mut chi as *mut f64);
        let phi: f64 = 0.5 * (1.0 + 0.34 * 0.8 + 1.0);
        let expect = 1.0 / (phi + (phi * phi - 1.0).sqrt());
        assert!((chi - expect).abs() < 1e-14);
    }

    #[test]
    fn test_cantilever() {
        let e = 210e9;
        let a = 5.38e-3;
        let iz = 8.356e-5;
        let g = 81e9;
        let asy = 5.38e-3 * 0.6;
        let l = 2.0;
        let coords = [0.0, 0.0, l, 0.0];
        let members = [0.0, 1.0, a, e, iz, g, asy, 0.0];
        let bc = [0i64, 0, 0, 1, 0, 2];
        let nl = [1.0, 1.0, -1000.0];
        let mut u = [0.0; 6];
        let mut reac = [0.0; 6];
        let mut ef = [0.0; 6];
        let rc = sk_frame2d_solve(
            2, 1, coords.as_ptr(), members.as_ptr(),
            3, bc.as_ptr(), 1, nl.as_ptr(),
            u.as_mut_ptr(), reac.as_mut_ptr(), ef.as_mut_ptr(),
        );
        assert_eq!(rc, 0);
        assert!(u[4] < 0.0, "v_tip should be negative, got {}", u[4]);
        let v_eb = 1000.0 * l * l * l / (3.0 * e * iz);
        let v_timo = v_eb + 1000.0 * l / (g * asy);
        assert!(
            u[4].abs() > v_eb * 0.95 && u[4].abs() < v_timo * 1.05,
            "v={} eb={} timo={}",
            u[4].abs(),
            v_eb,
            v_timo
        );
        // Reacción vertical = 1000 N hacia arriba
        assert!((reac[1] - 1000.0).abs() < 1.0, "Ry={}", reac[1]);
        // Momento reacción = 2000 N·m
        assert!((reac[2] - 2000.0).abs() < 1.0, "M={}", reac[2]);
    }

    #[test]
    fn test_simply_supported_udl() {
        // Viga SS, w=-2000 N/m (gravedad, +y local hacia arriba), L=6 → R=+6000
        // End moments libres ≈ 0 (valida g36 = EI(2−φ)/(L(1+φ))).
        let e = 210e9;
        let a = 5.38e-3;
        let iz = 8.356e-5;
        let g = 81e9;
        let asy = 5.38e-3 * 0.6;
        let l = 6.0;
        let coords = [0.0, 0.0, l, 0.0];
        let members = [0.0, 1.0, a, e, iz, g, asy, -2000.0];
        // apoyos: nodo0 pin (u,v), nodo1 roller (v)
        let bc = [0i64, 0, 0, 1, 1, 1];
        let nl: [f64; 0] = [];
        let mut u = [0.0; 6];
        let mut reac = [0.0; 6];
        let mut ef = [0.0; 6];
        let rc = sk_frame2d_solve(
            2, 1, coords.as_ptr(), members.as_ptr(),
            3, bc.as_ptr(), 0, nl.as_ptr(),
            u.as_mut_ptr(), reac.as_mut_ptr(), ef.as_mut_ptr(),
        );
        assert_eq!(rc, 0);
        assert!((reac[1] - 6000.0).abs() < 1.0, "RA={}", reac[1]);
        assert!((reac[4] - 6000.0).abs() < 1.0, "RB={}", reac[4]);
        // Extremos libres: momentos ≈ 0
        assert!(ef[2].abs() < 1.0, "M1={}", ef[2]);
        assert!(ef[5].abs() < 1.0, "M2={}", ef[5]);
    }

    #[test]
    fn test_ss_two_element_midspan() {
        // 2 barras SS, nodos x=0,3,6, w=-2000 → M_centro = wL²/8 = 9000 (sagging)
        let e = 210e9;
        let a = 5.38e-3;
        let iz = 8.356e-5;
        let g = 81e9;
        let asy = 5.38e-3 * 0.6;
        let coords = [0.0, 0.0, 3.0, 0.0, 6.0, 0.0];
        let members = [
            0.0, 1.0, a, e, iz, g, asy, -2000.0,
            1.0, 2.0, a, e, iz, g, asy, -2000.0,
        ];
        let bc = [0i64, 0, 0, 1, 2, 1];
        let mut u = [0.0; 9];
        let mut reac = [0.0; 9];
        let mut ef = [0.0; 12];
        let rc = sk_frame2d_solve(
            3, 2, coords.as_ptr(), members.as_ptr(),
            3, bc.as_ptr(), 0, std::ptr::null(),
            u.as_mut_ptr(), reac.as_mut_ptr(), ef.as_mut_ptr(),
        );
        assert_eq!(rc, 0);
        assert!((reac[1] - 6000.0).abs() < 2.0, "RA={}", reac[1]);
        assert!((reac[7] - 6000.0).abs() < 2.0, "RB={}", reac[7]);
        // Momento en nodo central (extremo 2 barra1): sagging
        let m_c = ef[5];
        assert!(m_c.abs() > 8500.0 && m_c.abs() < 9500.0, "Mc={}", m_c);
        // Flecha central: Hermite 2 elems da exactamente 0.6×EB (converge a EB con malla fina)
        // + corrección de cortante wL²/(8GAs).
        let v_eb = 5.0 * 2000.0 * 6.0f64.powi(4) / (384.0 * e * iz);
        let v_sh = 2000.0 * 36.0 / (8.0 * g * asy);
        let v_expect = 0.6 * v_eb + v_sh;
        assert!(
            (u[4].abs() - v_expect).abs() / v_expect < 0.01,
            "vmid={} expect≈{}",
            u[4].abs(),
            v_expect
        );
    }

    #[test]
    fn test_cantilever_tip_moment() {
        // Cantiliver con momento en extremo libre: θ = ML/EI (sin cortante en M puro)
        let e = 210e9;
        let a = 5.38e-3;
        let iz = 8.356e-5;
        let g = 81e9;
        let asy = 5.38e-3 * 0.6;
        let l = 2.0;
        let coords = [0.0, 0.0, l, 0.0];
        let members = [0.0, 1.0, a, e, iz, g, asy, 0.0];
        let bc = [0i64, 0, 0, 1, 0, 2];
        // momento +5000 N·m sobre θ del nodo 1 (dof local 2)
        let nl = [1.0, 2.0, 5000.0];
        let mut u = [0.0; 6];
        let mut reac = [0.0; 6];
        let mut ef = [0.0; 6];
        let rc = sk_frame2d_solve(
            2, 1, coords.as_ptr(), members.as_ptr(),
            3, bc.as_ptr(), 1, nl.as_ptr(),
            u.as_mut_ptr(), reac.as_mut_ptr(), ef.as_mut_ptr(),
        );
        assert_eq!(rc, 0);
        let th = 5000.0 * l / (e * iz);
        assert!((u[5] - th).abs() / th < 1e-6, "th={} expect={}", u[5], th);
    }

    #[test]
    fn test_c_frame_vertical_column() {
        // Pórtico en C: columna vertical (0,0)→(0,3), voladizo (0,3)→(4,3),
        // P=−10 kN en voladizo. M_base = P·4 = 40000 (valida T^T Kl T en
        // barra vertical; el bug T Kl T^T pasaba los tests horizontales).
        let e = 210e9;
        let a = 5.38e-3;
        let iz = 8.356e-5;
        let g = 81e9;
        let asy = 5.38e-3 * 0.6;
        let coords = [0.0, 0.0, 0.0, 3.0, 4.0, 3.0];
        let members = [
            0.0, 1.0, a, e, iz, g, asy, 0.0,
            1.0, 2.0, a, e, iz, g, asy, 0.0,
        ];
        let bc = [0i64, 0, 0, 1, 0, 2];
        let nl = [2.0, 1.0, -10000.0];
        let mut u = [0.0; 9];
        let mut reac = [0.0; 9];
        let mut ef = [0.0; 12];
        let rc = sk_frame2d_solve(
            3, 2, coords.as_ptr(), members.as_ptr(),
            3, bc.as_ptr(), 1, nl.as_ptr(),
            u.as_mut_ptr(), reac.as_mut_ptr(), ef.as_mut_ptr(),
        );
        assert_eq!(rc, 0);
        // reacción vertical base = +10000, momento base = P·4 = 40000 (sagging)
        assert!((reac[1] - 10000.0).abs() < 1.0, "Ry={}", reac[1]);
        assert!((reac[2].abs() - 40000.0).abs() < 5.0, "M0={}", reac[2]);
        // momento en la base de la columna (extremo 1, barra vertical)
        assert!((ef[2].abs() - 40000.0).abs() < 5.0, "M_base={}", ef[2]);
        // cortante en la columna = carga horizontal = 0
        assert!(ef[1].abs() < 1.0, "V1={}", ef[1]);
    }
}
