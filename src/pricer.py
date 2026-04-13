import numpy as np
from src.curve import DiscountCurve


def payer_swap_npv(forwards_at_Tk: np.ndarray,
                    tenor_dates: np.ndarray,
                    k: int, 
                    K: float) -> np.ndarray:
    """NPV of a payer swap starting at Tk, computed from simulated forwards.
    
    Uses the simulated forward rates to compute both the cashflows and the 
    path-dependent discount factors (by compounding forwards).
    
    Parameters
    ----------
    forwards_at_Tk : np.ndarray, shape (n_paths, N)
        Forward rates at time Tk, for each of the N forwards. 
        Forwards with index < k are unused (already expired) - set to NaN or 0.
    tenor_dates : np.ndarray, shape (N+1,)
        Tenor structure T_0, T_1, ..., T_N.
    k : int
        Index of the exercise date (swap starts at T_k, ends at T_N).
    K : float
        Fixed strike rate in decimal.
    
    Returns
    -------
    np.ndarray, shape (n_paths,)
        NPV of the remaining (N-k)-year payer swap on each path, viewed at time Tk.
        Positive means the payer swap is valuable (floating > fixed in expectation).
    
    Formula
    -------
    NPV_m = sum_{j=k}^{N-1} delta_j * DF_path(Tk, T_{j+1}) * (F_j(Tk, m) - K)
    where DF_path(Tk, T_{j+1}) = prod_{i=k}^{j} 1 / (1 + delta_i * F_i(Tk))
    """
    pass


def longstaff_schwartz_bermudan(simulation: dict,
                                  curve: DiscountCurve,
                                  K: float,
                                  exercise_indices: np.ndarray,
                                  basis_degree: int = 3,
                                  itm_only: bool = True) -> dict:
    """Price a Bermudan payer swaption via Longstaff-Schwartz LSMC.
    
    Works backward through exercise dates, using OLS regression on polynomial
    basis functions of the current swap rate to estimate continuation values.
    
    Parameters
    ----------
    simulation : dict
        Output of simulate_lmm(). Must contain 'forwards', 'timesteps', 'tenor_dates'.
    curve : DiscountCurve
        Used for the initial (t=0) discount factors.
    K : float
        Strike rate (typically the ATM par swap rate) in decimal.
    exercise_indices : np.ndarray of int, shape (n_exercise,)
        Indices into tenor_dates at which exercise is allowed.
        For 10nc1 with annual exercise: np.array([1, 2, 3, 4, 5, 6, 7, 8, 9]).
    basis_degree : int, default 3
        Polynomial degree for the LS regression basis {1, S, S^2, ..., S^d} 
        where S is the current swap rate.
    itm_only : bool, default True
        If True, regression uses only in-the-money paths (per Longstaff-Schwartz).
    
    Returns
    -------
    dict with keys:
        'price'          : float, Bermudan price in the same units as notional.
                            Typically reported in bps of notional (multiply by 10000).
        'std_error'      : float, Monte Carlo standard error.
        'exercise_probs' : np.ndarray, shape (n_exercise,)
                            Probability of exercising at each date.
        'european_price' : float, European swaption price (exercisable only at first date),
                            computed on same paths for comparison.
        'bermudan_premium': float, price - european_price.
    
    Algorithm
    ---------
    1. Initialize cashflows[m] = 0 for all paths m.
    2. At the final exercise date T_last, set cashflows[m] = max(0, IV(T_last, m)).
    3. Step backwards through exercise dates:
       a. Compute IV(T_k, m) for each path m.
       b. Identify ITM paths (IV > 0).
       c. Regress discounted future cashflows against [1, S, S^2, S^3] on ITM paths.
       d. For each ITM path, exercise if IV > predicted continuation value.
       e. Update cashflows[m] for exercising paths.
    4. Discount all cashflows to t=0 using path-dependent discount factors,
       average across paths.
    
    Example
    -------
    >>> result = longstaff_schwartz_bermudan(
    ...     simulation=lmm_result,
    ...     curve=curve,
    ...     K=0.0374,
    ...     exercise_indices=np.arange(1, 10)
    ... )
    >>> print(f"Bermudan: {result['price']*10000:.1f} bps")
    Bermudan: 347.2 bps
    >>> print(f"European: {result['european_price']*10000:.1f} bps")
    European: 298.4 bps
    >>> print(f"Premium: {result['bermudan_premium']*10000:.1f} bps")
    Premium: 48.8 bps
    """
    pass


def european_swaption_bachelier(curve: DiscountCurve,
                                 expiry: float, 
                                 tenor: float,
                                 K: float, 
                                 sigma_normal: float,
                                 payer: bool = True) -> float:
    """Analytical European swaption price under the Bachelier (normal) model.
    
    Used as a sanity check / benchmark against the Monte Carlo European price.
    
    Parameters
    ----------
    curve : DiscountCurve
    expiry : float
        Option expiry in years.
    tenor : float
        Length of underlying swap in years.
    K : float
        Strike rate.
    sigma_normal : float
        Normal implied vol (from SABR calibration).
    payer : bool, default True
        If True, payer (call); if False, receiver (put).
    
    Returns
    -------
    float
        Swaption price in same units as notional (fraction of notional).
    
    Formula
    -------
    Price = Annuity(0; expiry, tenor) * [(F - K) * Phi(d) + sigma*sqrt(T) * phi(d)]
    where d = (F - K) / (sigma*sqrt(T)), Phi is normal CDF, phi is normal PDF.
    """
    pass