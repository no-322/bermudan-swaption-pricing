import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from typing import Union
from src.curve import DiscountCurve


def hagan_normal_vol(F: float, K: float, T: float,
                     sigma0: float, beta: float, rho: float, nu: float) -> float:
    """Hagan (2002) asymptotic normal (Bachelier) implied vol for SABR.

    Parameters
    ----------
    F      : forward rate (decimal)
    K      : strike (decimal, > 0)
    T      : time to expiry (years, > 0)
    sigma0 : initial vol level (> 0)
    beta   : CEV exponent in [0, 1], typically 0.5
    rho    : correlation in (-1, 1)
    nu     : vol-of-vol (> 0)

    Returns
    -------
    float : normal implied vol in decimal (e.g. 0.0074 = 74 bps)
    """
    if T <= 0 or sigma0 <= 0:
        return 0.0

    # ATM case: K ≈ F
    if abs(K - F) < 1e-8:
        Fmid = F
        Fb = F ** beta
        # ATM normal vol = sigma0 * F^beta * [1 + correction * T]
        term1 = ((1 - beta) ** 2 / 24) * sigma0 ** 2 / (F ** (2 - 2 * beta))
        term2 = 0.25 * rho * beta * nu * sigma0 / Fb
        term3 = (2 - 3 * rho ** 2) / 24 * nu ** 2
        vol_n = sigma0 * Fb * (1 + (term1 + term2 + term3) * T)
        # Convert to normal vol: multiply by F for lognormal→normal
        # Actually for Hagan normal vol formula, the ATM value is:
        # sigma_N = sigma0 * F^beta * [1 + correction*T]
        # This IS already the normal vol when using the normal SABR expansion
        return vol_n

    # OTM / ITM case
    Fmid = np.sqrt(F * K)
    Fb = Fmid ** beta
    logFK = np.log(F / K)

    # zeta and x(zeta)
    zeta = (nu / sigma0) * Fb * logFK  # note: Fb here approximates (FK)^((1-beta)/2)
    # More precisely: zeta = (nu/sigma0) * (F^(1-beta) - K^(1-beta)) / (1-beta)
    if abs(1 - beta) > 1e-8:
        zeta = (nu / sigma0) * (F ** (1 - beta) - K ** (1 - beta)) / (1 - beta)
    else:
        zeta = (nu / sigma0) * logFK

    # x(zeta) — the mapping
    disc = 1 - 2 * rho * zeta + zeta ** 2
    if disc < 0:
        disc = 1e-10
    sqrt_disc = np.sqrt(disc)
    x_zeta = np.log((sqrt_disc + zeta - rho) / (1 - rho))
    if abs(x_zeta) < 1e-10:
        x_zeta = 1e-10

    # Numerator: sigma0 * (F-K)
    # with corrections
    FK_beta = (F * K) ** ((1 - beta) / 2)

    # 1 + correction terms
    term1 = ((1 - beta) ** 2 / 24) * sigma0 ** 2 / (FK_beta ** 2)
    term2 = 0.25 * rho * beta * nu * sigma0 / FK_beta
    term3 = (2 - 3 * rho ** 2) / 24 * nu ** 2

    vol_n = (sigma0 * (F - K) / (FK_beta * x_zeta)) * (zeta) * (1 + (term1 + term2 + term3) * T)

    # Simplified Hagan normal vol:
    # sigma_N = sigma0 * (F-K) / [FK^((1-b)/2) * x(zeta)] * zeta/1 * [1 + O(T)]
    # But the standard formula is:
    # sigma_N(K) = sigma0 * FK^(beta/2) * (zeta/x(zeta)) * [1 + corrections*T]
    # where the (F-K) enters through zeta.

    # Let me use the cleaner standard formulation:
    # Normal vol = sigma0 * Fmid^beta * (zeta / x_zeta) * [1 + corr*T]
    vol_n = sigma0 * FK_beta ** (beta / (1 - beta) if abs(1 - beta) > 1e-8 else 1) * (zeta / x_zeta) * (1 + (term1 + term2 + term3) * T)

    # Actually, let me implement this more carefully using the standard reference
    return abs(vol_n)


def _hagan_normal_vol_v2(F: float, K: float, T: float,
                          sigma0: float, beta: float, rho: float, nu: float) -> float:
    """Clean implementation of Hagan normal SABR vol.

    Uses the formulation from Hagan 2002 adapted for normal (Bachelier) vol output.
    The normal SABR implied vol formula is:

    sigma_N(K) = alpha * (1-beta) * (F-K) / (F^(1-beta) - K^(1-beta))
                 * (zeta / x(zeta))
                 * [1 + T * (correction terms)]

    where zeta = (nu/alpha) * (F^(1-beta) - K^(1-beta)) / (1-beta)
    and x(zeta) = log[(sqrt(1-2*rho*zeta+zeta^2) + zeta - rho) / (1-rho)]
    """
    if T <= 0 or sigma0 <= 0 or F <= 0 or K <= 0:
        return 0.0

    alpha = sigma0

    # ATM limit
    if abs(F - K) < 1e-8:
        Fb = F ** beta
        t1 = (1 - beta) ** 2 / 24 * alpha ** 2 * F ** (2 * beta - 2)
        t2 = rho * beta * nu * alpha / (4 * F ** (1 - beta))
        t3 = (2 - 3 * rho ** 2) * nu ** 2 / 24
        return alpha * Fb * (1 + (t1 + t2 + t3) * T)

    # General case
    if abs(1 - beta) < 1e-8:
        # Lognormal SABR limit (beta=1)
        logFK = np.log(F / K)
        zeta = nu / alpha * logFK
    else:
        one_m_b = 1 - beta
        F1mb = F ** one_m_b
        K1mb = K ** one_m_b
        zeta = nu / alpha * (F1mb - K1mb) / one_m_b

    # x(zeta)
    disc = 1 - 2 * rho * zeta + zeta ** 2
    if disc < 1e-12:
        disc = 1e-12
    sqrt_disc = np.sqrt(disc)
    arg = (sqrt_disc + zeta - rho) / (1 - rho)
    if arg <= 0:
        arg = 1e-10
    x_z = np.log(arg)

    if abs(x_z) < 1e-12:
        ratio = 1.0
    else:
        ratio = zeta / x_z

    # The (F-K) factor with (1-beta) correction
    if abs(1 - beta) < 1e-8:
        fk_factor = 1.0
    else:
        one_m_b = 1 - beta
        F1mb = F ** one_m_b
        K1mb = K ** one_m_b
        if abs(F1mb - K1mb) < 1e-12:
            fk_factor = F ** beta
        else:
            fk_factor = one_m_b * (F - K) / (F1mb - K1mb)

    # Correction terms
    FK_mid = np.sqrt(F * K)
    FK_beta_mid = FK_mid ** ((1 - beta))

    t1 = (1 - beta) ** 2 / 24 * alpha ** 2 / FK_beta_mid ** 2
    t2 = rho * beta * nu * alpha / (4 * FK_beta_mid)
    t3 = (2 - 3 * rho ** 2) * nu ** 2 / 24

    sigma_n = alpha * fk_factor * ratio * (1 + (t1 + t2 + t3) * T)
    return abs(sigma_n)


# Use the clean v2 implementation
hagan_normal_vol = _hagan_normal_vol_v2


def calibrate_sabr_slice(F: float, T: float,
                          strikes: np.ndarray, market_vols: np.ndarray,
                          beta: float = 0.5) -> dict:
    """Calibrate SABR parameters (sigma0, rho, nu) for one (expiry, tenor) pair.

    Parameters
    ----------
    F           : forward swap rate (decimal)
    T           : time to expiry (years)
    strikes     : array of absolute strikes (decimal)
    market_vols : array of market normal vols (decimal, e.g. 0.0087 = 87bp)
    beta        : CEV exponent, fixed

    Returns
    -------
    dict with sigma0, rho, nu, beta, rmse, success
    """
    strikes = np.asarray(strikes, dtype=float)
    market_vols = np.asarray(market_vols, dtype=float)

    # Filter out any NaN or zero vols
    mask = np.isfinite(market_vols) & (market_vols > 0) & np.isfinite(strikes) & (strikes > 0)
    strikes = strikes[mask]
    market_vols = market_vols[mask]

    if len(strikes) < 3:
        return {'sigma0': np.nan, 'rho': np.nan, 'nu': np.nan,
                'beta': beta, 'rmse': np.inf, 'success': False}

    # Find ATM vol (closest strike to F)
    atm_idx = np.argmin(np.abs(strikes - F))
    atm_vol = market_vols[atm_idx]

    # Initial guesses
    x0 = np.array([atm_vol, -0.3, 0.4])

    def residuals(params):
        s0, rho, nu = params
        model_vols = np.array([
            hagan_normal_vol(F, K, T, s0, beta, rho, nu) for K in strikes
        ])
        return model_vols - market_vols

    try:
        result = least_squares(
            residuals, x0,
            bounds=([1e-6, -0.999, 1e-6], [1.0, 0.999, 5.0]),
            method='trf', max_nfev=500
        )
        sigma0, rho, nu = result.x
        rmse = np.sqrt(np.mean(result.fun ** 2))
        return {
            'sigma0': sigma0, 'rho': rho, 'nu': nu,
            'beta': beta, 'rmse': rmse, 'success': result.success
        }
    except Exception:
        return {'sigma0': np.nan, 'rho': np.nan, 'nu': np.nan,
                'beta': beta, 'rmse': np.inf, 'success': False}


def calibrate_full_surface(curve: DiscountCurve,
                            vol_cube: pd.DataFrame,
                            beta: float = 0.5) -> pd.DataFrame:
    """Calibrate SABR across all (expiry, tenor) pairs in the vol cube.

    Parameters
    ----------
    curve    : DiscountCurve
    vol_cube : DataFrame with columns:
               expiry_years, tenor_years, strike_offset (decimal), market_vol (decimal)
    beta     : fixed CEV exponent

    Returns
    -------
    DataFrame indexed by (expiry_years, tenor_years) with columns:
    F, sigma0, rho, nu, beta, rmse, success
    """
    results = []
    groups = vol_cube.groupby(['expiry_years', 'tenor_years'])

    for (exp, ten), grp in groups:
        F = curve.par_swap_rate(exp, ten, freq=0.5)
        strikes = F + grp['strike_offset'].values
        mkt_vols = grp['market_vol'].values

        res = calibrate_sabr_slice(F, exp, strikes, mkt_vols, beta)
        res['F'] = F
        res['expiry_years'] = exp
        res['tenor_years'] = ten
        results.append(res)

    out = pd.DataFrame(results)
    out = out.set_index(['expiry_years', 'tenor_years'])
    return out[['F', 'sigma0', 'rho', 'nu', 'beta', 'rmse', 'success']]


def sabr_smile(F: float, T: float, strikes: np.ndarray,
               sigma0: float, beta: float, rho: float, nu: float) -> np.ndarray:
    """Evaluate SABR normal vol across a vector of strikes."""
    strikes = np.asarray(strikes, dtype=float)
    return np.array([hagan_normal_vol(F, K, T, sigma0, beta, rho, nu) for K in strikes])
