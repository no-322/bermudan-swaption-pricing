import numpy as np
import pandas as pd
from datetime import date
from typing import Union


class DiscountCurve:
    """SOFR OIS discount curve built from market instruments.
    
    Attributes
    ----------
    pricing_date : datetime.date
        The reference date. All times are measured in years from this date.
    instruments : pd.DataFrame
        The raw market data used to build the curve (stored for reference).
    pillar_dates : np.ndarray of floats
        Time-to-maturity in years for each curve pillar (e.g., [0.25, 0.5, ..., 30.0]).
    discount_factors : np.ndarray of floats
        Discount factor at each pillar date.
    """
    
    def __init__(self, pricing_date: date, instruments: pd.DataFrame):
        """Build curve from market data.
        
        Parameters
        ----------
        pricing_date : datetime.date
            Valuation date, e.g., date(2026, 3, 18).
        instruments : pd.DataFrame
            Must contain the following columns:
            - 'instrument_type' : str, one of {'futures', 'swap'}
            - 'maturity_years'  : float, time to maturity in years from pricing_date
            - 'rate'            : float, market rate in decimal (e.g., 0.0365 for 3.65%)
            - 'convexity_adj'   : float, in decimal; 0.0 for swaps (only used for futures)
            
            Example rows:
                instrument_type  maturity_years  rate      convexity_adj
                futures          0.25            0.036567  0.005460
                futures          0.50            0.036702  0.005236
                ...
                swap             2.0             0.035065  0.0
                swap             5.0             0.034979  0.0
                swap             10.0            0.037400  0.0
        
        Raises
        ------
        ValueError if instruments table is missing required columns or has non-monotonic maturities.
        """
        pass
    
    def df(self, t: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        """Discount factor from pricing date to time t.
        
        Uses log-linear interpolation between pillars.
        
        Parameters
        ----------
        t : float or np.ndarray
            Time(s) in years. Must be >= 0. Can be scalar or array.
        
        Returns
        -------
        float or np.ndarray
            Discount factor(s), each in (0, 1]. df(0) = 1.0 exactly.
        
        Examples
        --------
        >>> curve.df(1.0)
        0.9642
        >>> curve.df(np.array([1.0, 2.0, 5.0]))
        array([0.9642, 0.9312, 0.8156])
        """
        pass
    
    def forward_rate(self, t1: float, t2: float) -> float:
        """Simply-compounded forward rate between t1 and t2.
        
        Formula: F(t1, t2) = (DF(t1)/DF(t2) - 1) / (t2 - t1)
        
        Parameters
        ----------
        t1 : float
            Start time in years. Must be >= 0.
        t2 : float
            End time in years. Must be > t1.
        
        Returns
        -------
        float
            Forward rate in decimal (e.g., 0.037 = 3.7%).
        
        Examples
        --------
        >>> curve.forward_rate(1.0, 2.0)
        0.0352
        """
        pass
    
    def par_swap_rate(self, start: float, tenor: float, freq: float = 1.0) -> float:
        """ATM par swap rate for a swap starting at `start` with length `tenor`.
        
        The par rate K makes the fixed leg NPV equal to the float leg NPV:
            K = (DF(start) - DF(start+tenor)) / annuity(start, tenor, freq)
        
        Parameters
        ----------
        start : float
            Time to swap start in years (0 for spot-starting, >0 for forward-starting).
        tenor : float
            Length of the swap in years.
        freq : float, default 1.0
            Payment frequency in years (1.0 = annual, 0.5 = semi-annual).
        
        Returns
        -------
        float
            Par swap rate in decimal.
        
        Examples
        --------
        >>> curve.par_swap_rate(start=1.0, tenor=9.0)  # 1Y forward-starting 9Y swap
        0.0374
        """
        pass
    
    def annuity(self, start: float, tenor: float, freq: float = 1.0) -> float:
        """Annuity factor: sum of discounted year fractions over fixed-leg coupons.
        
        A = sum_{i=1}^{N} delta_i * DF(start + i*freq)
        where N = tenor / freq and delta_i = freq (assuming uniform year fractions).
        
        Parameters
        ----------
        start : float
            Time to swap start in years.
        tenor : float
            Length of swap in years.
        freq : float, default 1.0
            Payment frequency in years.
        
        Returns
        -------
        float
            Annuity factor (positive, units of years).
        """
        pass
    
    def zero_rate(self, t: float) -> float:
        """Continuously-compounded zero rate for maturity t.
        
        z(t) = -ln(DF(t)) / t
        
        Returns in decimal. Used primarily for validation/plotting.
        """
        pass