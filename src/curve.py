import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline
from datetime import date
from typing import Union


class DiscountCurve:
    """SOFR OIS discount curve built from zero-rate pillars.

    Supports two construction paths:
      1. from_zero_curve() — build from a zero-rate table (Bloomberg stripped curve)
      2. from_market_data() — bootstrap from swap rates + futures

    Attributes
    ----------
    pricing_date : datetime.date
    pillar_times : np.ndarray — time in years for each pillar
    zero_rates   : np.ndarray — continuously compounded zero rates (decimal)
    _cs          : CubicSpline interpolant on zero rates
    """

    def __init__(self, pricing_date: date, pillar_times: np.ndarray,
                 zero_rates: np.ndarray):
        """Direct constructor from arrays of pillar times and zero rates.

        Parameters
        ----------
        pricing_date : date
        pillar_times : array, shape (n,), in years, must start at 0 or near 0
        zero_rates   : array, shape (n,), continuously compounded, decimal
        """
        self.pricing_date = pricing_date
        self.pillar_times = np.asarray(pillar_times, dtype=float)
        self.zero_rates = np.asarray(zero_rates, dtype=float)
        self._cs = CubicSpline(self.pillar_times, self.zero_rates)

    # ── Factory: build from Bloomberg stripped zero curve CSV ──────────────
    @classmethod
    def from_zero_curve(cls, pricing_date: date, zero_df: pd.DataFrame):
        """Build curve from a DataFrame with columns: date, zero_rate, discount_factor.

        zero_rate is in percent (e.g. 3.70 = 3.70%). Dates are parsed to compute T.
        """
        df = zero_df.copy()
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            pricing_ts = pd.Timestamp(pricing_date)
            df['T'] = (df['date'] - pricing_ts).dt.days / 360.0
            df = df[df['T'] > 0].copy()

        T = np.concatenate([[0.0], df['T'].values])
        Z = np.concatenate([[df['zero_rate'].iloc[0] / 100.0],
                            df['zero_rate'].values / 100.0])
        return cls(pricing_date, T, Z)

    # ── Factory: bootstrap from market instruments ────────────────────────
    @classmethod
    def from_market_data(cls, pricing_date: date, swap_rates: pd.DataFrame,
                         futures: pd.DataFrame = None):
        """Bootstrap a discount curve from swap rates (and optionally futures).

        Parameters
        ----------
        pricing_date : date
        swap_rates : DataFrame with columns: term, mid (rate in %)
            term is like '1D','1W','1M','2Y','10Y', mid is the mid rate in percent.
        futures : DataFrame with columns: maturity_years, implied_rate (decimal)
            Optional futures for the front end.
        """
        from src.utils import term_to_years

        sr = swap_rates.copy()
        if 'mid' not in sr.columns and 'bid' in sr.columns:
            sr['mid'] = (sr['bid'] + sr['ask']) / 2.0
        sr['T'] = sr['term'].apply(term_to_years)
        sr = sr.sort_values('T').reset_index(drop=True)
        sr['mid_dec'] = sr['mid'] / 100.0

        T_k = [0.0]
        DF_k = [1.0]
        Z_k = [sr.iloc[0]['mid_dec']]  # overnight rate anchor

        def _get_df(T):
            z = np.interp(T, T_k, Z_k)
            return np.exp(-z * T) if T > 0 else 1.0

        for _, row in sr.iterrows():
            T = row['T']
            S = row['mid_dec']
            if T <= 0:
                continue
            if T <= 1.0:
                DF = 1.0 / (1.0 + S * T)
            else:
                n = int(round(T))
                pay_T = np.arange(1, n + 1, dtype=float)
                annuity = sum(_get_df(t) for t in pay_T[:-1])
                DF = (1.0 - S * annuity) / (1.0 + S)
                if DF <= 0:
                    continue
            Z = -np.log(DF) / T
            T_k.append(T)
            DF_k.append(DF)
            Z_k.append(Z)

        pairs = sorted(set(zip(T_k, Z_k)))
        T_arr = np.array([p[0] for p in pairs])
        Z_arr = np.array([p[1] for p in pairs])
        return cls(pricing_date, T_arr, Z_arr)

    # ── Core methods ──────────────────────────────────────────────────────

    def df(self, t: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        """Discount factor at time t (years). Log-linear via cubic spline on zero rates."""
        t = np.asarray(t, dtype=float)
        scalar = t.ndim == 0
        t = np.atleast_1d(t)
        z = np.maximum(self._cs(t), 1e-6)
        result = np.where(t <= 0, 1.0, np.exp(-z * t))
        return float(result[0]) if scalar else result

    def forward_rate(self, t1: float, t2: float) -> float:
        """Simply-compounded forward rate F(t1, t2)."""
        if t2 <= t1:
            raise ValueError(f"t2={t2} must be > t1={t1}")
        return (self.df(t1) / self.df(t2) - 1.0) / (t2 - t1)

    def par_swap_rate(self, start: float, tenor: float, freq: float = 0.5) -> float:
        """ATM par swap rate: K = (DF(start) - DF(start+tenor)) / annuity."""
        ann = self.annuity(start, tenor, freq)
        if ann <= 0:
            return 0.0
        return (self.df(start) - self.df(start + tenor)) / ann

    def annuity(self, start: float, tenor: float, freq: float = 0.5) -> float:
        """Annuity factor: sum of delta_i * DF(start + i*freq)."""
        n_periods = max(1, int(round(tenor / freq)))
        pay_times = start + np.arange(1, n_periods + 1) * freq
        return float(np.sum(freq * self.df(pay_times)))

    def zero_rate(self, t: float) -> float:
        """Continuously-compounded zero rate at maturity t."""
        if t <= 0:
            return float(self._cs(0.0))
        return float(-np.log(self.df(t)) / t)
