import numpy as np
import pandas as pd
from typing import Union
# from src.curve import DiscountCurve
from scipy.optimize import least_squares


import numpy as np


def hagan_normal_vol(F: float, K: float, T: float,
                     sigma0: float, beta: float,
                     rho: float, nu: float) -> float:
    """Hagan (2002) asymptotic approximation for SABR normal implied vol.

    Implements the normal (Bachelier) implied vol formula from Hagan et al. 2002,
    "Managing Smile Risk", Appendix A, Eq. (A.67), specialized to CEV local vol C(F) = F^beta.

    Parameters
    ----------
    F : float
        Forward rate in decimal (e.g., forward swap rate).
    K : float
        Strike in decimal. Must be > 0.
    T : float
        Time to expiry in years. Must be > 0.
    sigma0 : float
        Initial stochastic volatility level. Must be > 0.
    beta : float
        CEV exponent in [0, 1]. Typically fixed at 0.5.
    rho : float
        Correlation between rate and vol. Must be in (-1, 1).
    nu : float
        Vol-of-vol. Must be > 0.

    Returns
    -------
    float
        Normal (Bachelier) implied volatility in decimal (e.g., 0.0074 = 74 bps).

    Notes
    -----
    - When |K - F| < 1e-10, uses the ATM closed-form limit to avoid 0/0.
    - Reference: Hagan et al. (2002), "Managing Smile Risk", Wilmott Magazine.
    """
    # --- Input sanity ---
    if K <= 0:
        raise ValueError(f"Strike K must be positive, got K={K}")
    if F <= 0:
        raise ValueError(f"Forward F must be positive, got F={F}")
    # Clip rho slightly inside (-1, 1) for numerical stability
    rho = np.clip(rho, -0.9999, 0.9999)

    # --- Correction terms ---
    # Use F_mid = sqrt(F*K)
    F_mid = np.sqrt(F * K)

    term_A = -beta * (2.0 - beta) * sigma0**2 / (24.0 * F_mid**(2.0 - 2.0*beta))
    term_B = rho * beta * sigma0 * nu / (4.0 * F_mid**(1.0 - beta))
    term_C = (2.0 - 3.0 * rho**2) * nu**2 / 24.0

    correction = 1.0 + (term_A + term_B + term_C) * T

    # --- ATM case ---
    if abs(F - K) < 1e-10:
        sigma_leading = sigma0 * F**beta
        return sigma_leading * correction

    # --- General case ---
    zeta = (nu / sigma0) * (F - K) * F_mid**(-beta)
    chi = np.log(
        (np.sqrt(1.0 - 2.0 * rho * zeta + zeta**2) + zeta - rho)
        / (1.0 - rho)
    )

    sigma_leading = sigma0 * F_mid**beta * (zeta / chi)

    return sigma_leading * correction
    


def calibrate_sabr_slice(F: float, T: float, 
                          strikes: np.ndarray, market_vols: np.ndarray, 
                          beta: float = 0.5) -> dict:
    """Calibrate SABR parameters (sigma0, rho, nu) for a single (expiry, tenor) point.
    
    Minimizes sum of squared errors between Hagan-implied vols and market vols
    across strikes, using scipy.optimize.least_squares.
    
    Parameters
    ----------
    F : float
        Forward swap rate (ATM strike) in decimal.
    T : float
        Time to expiry in years.
    strikes : np.ndarray of floats, shape (n_strikes,)
        Absolute strikes in decimal (e.g., [F-0.0025, F, F+0.0025] for ±25bp).
    market_vols : np.ndarray of floats, shape (n_strikes,)
        Observed market normal vols in decimal, same shape as strikes.
    beta : float, default 0.5
        CEV exponent, held fixed during calibration.
    
    Returns
    -------
    dict with keys:
        'sigma0' : float, calibrated initial vol
        'rho'    : float, calibrated correlation in (-1, 1)
        'nu'     : float, calibrated vol-of-vol
        'beta'   : float, the fixed beta used
        'rmse'   : float, root-mean-squared fit error in decimal vol
        'success': bool, whether optimizer converged
    
    Notes
    -----
    - Initial guesses: sigma0=market_atm_vol, rho=-0.3, nu=0.4.
    - Bounds: sigma0 in (1e-6, 1.0), rho in (-0.999, 0.999), nu in (1e-6, 5.0).
    """
    def residuals(params):
        sigma0, rho, nu = params
        model_vols = np.array([
            hagan_normal_vol(F, K, T, sigma0, beta, rho, nu)
            for K in strikes
        ])
        return model_vols - market_vols
    
    atm_idx = np.argmin(np.abs(strikes - F))

    # Initial guess for sigmo, rho and nu based on historic data
    sigma0_init = market_vols[atm_idx] / (F**beta)
    x0 = [sigma0_init, -0.3, 0.4]

    bounds = ([1e-6, -0.999, 1e-6], [2.0, 0.999, 5.0])

    result = least_squares(residuals, x0, bounds=bounds, method='trf')

    sigma0_fit, rho_fit, nu_fit = result.x
    rmse = np.sqrt(np.mean(result.fun**2))
    return {
        'sigma0': sigma0_fit,
        'rho': rho_fit,
        'nu': nu_fit,
        'rmse': rmse,
        'success': result.success
    }


def calibrate_full_surface(curve: DiscountCurve, 
                             vol_cube: pd.DataFrame, 
                             beta: float = 0.5) -> pd.DataFrame:
    """Calibrate SABR parameters across the full swaption vol grid.
    
    Loops over all (expiry, tenor) pairs, computes the forward swap rate from
    the curve, and calibrates SABR to the smile at each pair.
    
    Parameters
    ----------
    curve : DiscountCurve
        The discount curve, used to compute forward swap rates.
    vol_cube : pd.DataFrame
        Must contain columns:
        - 'expiry_years'  : float, option expiry in years
        - 'tenor_years'   : float, underlying swap tenor in years
        - 'strike_offset' : float, strike offset from ATM in decimal 
                             (e.g., 0.0025 for +25bp, 0.0 for ATM)
        - 'market_vol'    : float, market normal vol in decimal
        
        Must contain at least 3 strike points per (expiry, tenor) for calibration.
        
        Example rows:
            expiry_years  tenor_years  strike_offset  market_vol
            1.0           5.0          -0.0025        0.00702
            1.0           5.0           0.0           0.00740
            1.0           5.0           0.0025        0.00792
            ...
    beta : float, default 0.5
        CEV exponent, held fixed.
    
    Returns
    -------
    pd.DataFrame
        Indexed by (expiry_years, tenor_years) MultiIndex, with columns:
        - 'F'      : float, ATM forward swap rate at this point
        - 'sigma0' : float
        - 'rho'    : float
        - 'nu'     : float
        - 'beta'   : float
        - 'rmse'   : float, fit quality
        - 'success': bool
    
    Notes
    -----
    - If a (expiry, tenor) calibration fails, rmse=np.inf and success=False.
    - The output DataFrame becomes an input to the LMM simulation (Layer 3).
    """
    
    pass


def sabr_smile(F: float, T: float, strikes: np.ndarray, 
                sigma0: float, beta: float, rho: float, nu: float) -> np.ndarray:
    """Evaluate the full SABR smile at a vector of strikes. 
    
    Convenience wrapper around hagan_normal_vol. Used for plotting model vs market.
    
    Parameters
    ----------
    F, T : float
        Forward and expiry.
    strikes : np.ndarray, shape (n_strikes,)
        Absolute strikes.
    sigma0, beta, rho, nu : float
        SABR parameters.
    
    Returns
    -------
    np.ndarray, shape (n_strikes,)
        Normal implied vols at each strike.
    """
    pass

if __name__ == "__main__":
    pass

