import numpy as np
import pandas as pd
from src.curve import DiscountCurve


def build_correlation_matrix(tenors: np.ndarray, lam: float = 0.05) -> np.ndarray:
    """Parametric exponential decay correlation matrix for forward rates.

    rho_{ij} = exp(-lam * |T_i - T_j|)

    Parameters
    ----------
    tenors : np.ndarray, shape (N,)
        Forward rate tenor dates in years.
    lam : float, default 0.05
        Correlation decay parameter.

    Returns
    -------
    np.ndarray, shape (N, N)
        Symmetric positive-definite correlation matrix.
    """
    N = len(tenors)
    T = np.asarray(tenors, dtype=float)
    return np.exp(-lam * np.abs(T[:, None] - T[None, :]))


def simulate_lmm(curve: DiscountCurve,
                  sabr_params: pd.DataFrame,
                  tenor_structure: np.ndarray,
                  n_paths: int = 50000,
                  dt: float = 0.25,
                  correlation_lambda: float = 0.05,
                  seed: int = 42,
                  antithetic: bool = True) -> dict:
    """Simulate joint evolution of forward SOFR rates under the terminal forward measure.

    Parameters
    ----------
    curve            : DiscountCurve — initial curve for F_i(0)
    sabr_params      : DataFrame indexed by (expiry_years, tenor_years) with 'sigma0' column
    tenor_structure  : array shape (N+1,) — tenor dates T_0 < T_1 < ... < T_N
    n_paths          : number of MC paths
    dt               : time step in years
    correlation_lambda : exponential decay parameter for forward correlation
    seed             : random seed
    antithetic       : use antithetic variates

    Returns
    -------
    dict with keys: forwards, timesteps, tenor_dates, corr_matrix, vols
    """
    tenor_structure = np.asarray(tenor_structure, dtype=float)
    N = len(tenor_structure) - 1  # number of forward rates
    T_max = tenor_structure[-1]

    # Time grid
    n_steps = int(np.ceil(T_max / dt))
    timesteps = np.linspace(0, T_max, n_steps + 1)
    actual_dt = timesteps[1] - timesteps[0]

    # Accrual fractions: delta_i = T_{i+1} - T_i
    deltas = np.diff(tenor_structure)

    # Initial forward rates: F_i(0) = (DF(T_i)/DF(T_{i+1}) - 1) / delta_i
    forwards_0 = np.array([
        curve.forward_rate(tenor_structure[i], tenor_structure[i + 1])
        for i in range(N)
    ])

    # ATM vols from SABR params — for each forward F_i, we need the ATM
    # normal vol, then convert to lognormal vol for the log-Euler step.
    # SABR sigma0 (alpha) is NOT the normal vol — we must evaluate Hagan's
    # formula at ATM to get sigma_N, then sigma_LN = sigma_N / F_i(0).
    from src.sabr import hagan_normal_vol as _hagan

    vols = np.zeros(N)  # these will be LOGNORMAL vols for log-Euler
    normal_vols = np.zeros(N)  # store normal vols for reference

    if sabr_params is not None and len(sabr_params) > 0:
        sabr_idx = sabr_params.index  # MultiIndex (expiry_years, tenor_years)
        for i in range(N):
            T_exp = tenor_structure[i]
            T_ten = tenor_structure[-1] - tenor_structure[i]
            if T_exp <= 0:
                T_exp = 0.25

            # Find closest SABR params
            best_dist = np.inf
            best_row = None
            for (e, t) in sabr_idx:
                dist = abs(e - T_exp) + abs(t - T_ten)
                if dist < best_dist:
                    best_dist = dist
                    best_row = sabr_params.loc[(e, t)]

            if best_row is not None:
                s0 = best_row['sigma0']
                rho = best_row['rho']
                nu = best_row['nu']
                F_i = forwards_0[i]
                # Get ATM normal vol from Hagan formula
                sigma_N = _hagan(F_i, F_i, max(T_exp, 0.01), s0, 0.5, rho, nu)
                normal_vols[i] = sigma_N
                # Convert normal vol to lognormal: sigma_LN = sigma_N / F
                vols[i] = sigma_N / F_i if F_i > 1e-8 else 0.25
            else:
                vols[i] = 0.25  # default ~25% lognormal
    else:
        vols[:] = 0.25

    # Correlation matrix and Cholesky decomposition
    # Use midpoints of forward rate intervals for correlation
    tenor_mids = 0.5 * (tenor_structure[:-1] + tenor_structure[1:])
    corr = build_correlation_matrix(tenor_mids, correlation_lambda)
    L_chol = np.linalg.cholesky(corr)

    # Determine effective path count (double if antithetic)
    rng = np.random.default_rng(seed)
    if antithetic:
        n_half = n_paths // 2
        n_paths_eff = 2 * n_half
    else:
        n_half = n_paths
        n_paths_eff = n_paths

    # Allocate forward rate array: (n_paths, n_steps+1, N)
    fwd = np.zeros((n_paths_eff, n_steps + 1, N))
    fwd[:, 0, :] = forwards_0[None, :]

    # Simulate
    for step in range(n_steps):
        t = timesteps[step]

        # Generate correlated normals
        Z_indep = rng.standard_normal((n_half, N))
        Z_corr_half = Z_indep @ L_chol.T  # (n_half, N)

        if antithetic:
            Z_corr = np.concatenate([Z_corr_half, -Z_corr_half], axis=0)
        else:
            Z_corr = Z_corr_half

        F_curr = fwd[:, step, :]  # (n_paths, N)

        for i in range(N):
            # Skip expired forwards: if t >= T_i, forward F_i has fixed
            if t >= tenor_structure[i]:
                fwd[:, step + 1, i] = F_curr[:, i]  # carry forward (frozen)
                continue

            sigma_i = vols[i]

            # HJM drift under terminal measure T_N
            # mu_i = -sum_{j=i+1}^{N-1} [delta_j * sigma_i * sigma_j * rho_{ij} * F_j]
            #         / (1 + delta_j * F_j)
            # Note: under terminal measure, the drift is negative (discount bond numeraire)
            # Actually the standard formula under T_N-forward measure:
            # mu_i(t) = -sigma_i * sum_{j=i+1}^{N-1} [delta_j * F_j(t) * sigma_j * rho_{ij}]
            #            / (1 + delta_j * F_j(t))
            drift = 0.0
            for j in range(i + 1, N):
                if t >= tenor_structure[j]:
                    continue
                sigma_j = vols[j]
                rho_ij = corr[i, j]
                Fj = F_curr[:, j]
                dj = deltas[j]
                drift += dj * Fj * sigma_j * rho_ij / (1.0 + dj * Fj)

            drift = -sigma_i * drift  # (n_paths,) or scalar

            # Log-Euler step
            # F_i(t+dt) = F_i(t) * exp((mu_i - 0.5*sigma_i^2)*dt + sigma_i*sqrt(dt)*Z_i)
            log_step = (drift - 0.5 * sigma_i ** 2) * actual_dt + sigma_i * np.sqrt(actual_dt) * Z_corr[:, i]
            fwd[:, step + 1, i] = F_curr[:, i] * np.exp(log_step)

    # Mark expired forwards as NaN for clarity
    for step_idx in range(n_steps + 1):
        t = timesteps[step_idx]
        for i in range(N):
            if t > tenor_structure[i] + 1e-8:
                fwd[:, step_idx, i] = np.nan

    return {
        'forwards': fwd,
        'timesteps': timesteps,
        'tenor_dates': tenor_structure.copy(),
        'corr_matrix': corr,
        'vols': vols,
    }
