import numpy as np
import pandas as pd
from src.curve import DiscountCurve


def build_correlation_matrix(tenors: np.ndarray, lam: float = 0.05) -> np.ndarray:
    """Parametric exponential decay correlation matrix for forward rates.
    
    rho_{ij} = exp(-lam * |T_i - T_j|)
    
    Parameters
    ----------
    tenors : np.ndarray, shape (N,)
        Forward rate tenor dates in years (e.g., [1, 2, 3, ..., 10]).
    lam : float, default 0.05
        Correlation decay parameter. Higher = less correlated distant forwards.
    
    Returns
    -------
    np.ndarray, shape (N, N)
        Symmetric positive-definite correlation matrix.
    """
    pass


def simulate_lmm(curve: DiscountCurve, 
                  sabr_params: pd.DataFrame,
                  tenor_structure: np.ndarray,
                  n_paths: int = 50000, 
                  dt: float = 0.25,
                  correlation_lambda: float = 0.05, 
                  seed: int = 42,
                  antithetic: bool = True) -> dict:
    """Simulate joint evolution of forward SOFR rates under the terminal forward measure.
    
    Each forward rate evolves under log-normal dynamics:
        dF_i / F_i = mu_i(t) dt + sigma_i dW_i
    where sigma_i is taken from the SABR-calibrated ATM vol at (T_i, 1Y) and
    mu_i is the HJM no-arbitrage drift under the terminal measure.
    
    Parameters
    ----------
    curve : DiscountCurve
        Initial curve for extracting F_i(0).
    sabr_params : pd.DataFrame
        Output of calibrate_full_surface. Used to extract ATM vols for each forward.
    tenor_structure : np.ndarray, shape (N+1,)
        Tenor dates T_0 < T_1 < ... < T_N in years. Forward F_i covers [T_i, T_{i+1}].
        For a 10nc1 Bermudan with annual exercise: [0, 1, 2, ..., 10].
    n_paths : int, default 50000
        Number of Monte Carlo paths.
    dt : float, default 0.25
        Time step in years.
    correlation_lambda : float, default 0.05
        Correlation decay parameter for the forward rate correlation matrix.
    seed : int, default 42
        Random seed for reproducibility.
    antithetic : bool, default True
        If True, use antithetic variates (pairs of +Z and -Z paths).
    
    Returns
    -------
    dict with keys:
        'forwards'   : np.ndarray, shape (n_paths, n_timesteps+1, N)
                       Simulated forward rates. forwards[m, t, i] = F_i at time step t on path m.
                       Forwards that have passed their fixing date are set to NaN.
        'timesteps'  : np.ndarray, shape (n_timesteps+1,)
                       Time grid in years (0, dt, 2*dt, ..., T_N).
        'tenor_dates': np.ndarray, shape (N+1,)
                       The input tenor_structure, copied for downstream use.
        'corr_matrix': np.ndarray, shape (N, N)
                       The correlation matrix used.
        'vols'       : np.ndarray, shape (N,)
                       The per-forward vols used (from SABR).
    
    Notes
    -----
    - Drift convention: terminal forward measure T_N. Only F_{N-1} is driftless.
    - Simulation uses Euler-Maruyama with log-Euler step:
        F_i(t+dt) = F_i(t) * exp((mu_i - 0.5*sigma_i^2)*dt + sigma_i*sqrt(dt)*Z_i)
    - The output `forwards` array is the primary input to the Bermudan pricer.
    
    Example
    -------
    >>> result = simulate_lmm(curve, sabr_params, tenor_structure=np.arange(11))
    >>> result['forwards'].shape
    (50000, 41, 10)  # 50K paths, 40 quarterly steps + t=0, 10 forwards
    """
    pass