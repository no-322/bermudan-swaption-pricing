import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from typing import Union
from src.curve import DiscountCurve


def hagan_normal_vol(F: float, K: float, T: float,
                      sigma0: float, beta: float, rho: float, nu: float) -> float:
    """Hagan (2002) normal SABR implied vol. Appendix A, Eq. (A.67).

    Returns normal (Bachelier) vol in decimal. Uses L'Hopital at ATM.
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
