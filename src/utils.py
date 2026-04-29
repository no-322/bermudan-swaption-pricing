import numpy as np
from datetime import date, timedelta


def year_fraction(d1: date, d2: date, convention: str = 'ACT/360') -> float:
    """Year fraction between two dates under the given day count convention.

    Parameters
    ----------
    d1, d2 : datetime.date
        Start and end dates. Must have d2 >= d1.
    convention : str, default 'ACT/360'
        One of {'ACT/360', 'ACT/365', '30/360'}.

    Returns
    -------
    float
        Year fraction.
    """
    if convention == 'ACT/360':
        return (d2 - d1).days / 360.0
    elif convention == 'ACT/365':
        return (d2 - d1).days / 365.0
    elif convention == '30/360':
        y1, m1, d1_day = d1.year, d1.month, min(d1.day, 30)
        y2, m2, d2_day = d2.year, d2.month, min(d2.day, 30)
        if d1_day == 31:
            d1_day = 30
        if d2_day == 31 and d1_day >= 30:
            d2_day = 30
        return (360 * (y2 - y1) + 30 * (m2 - m1) + (d2_day - d1_day)) / 360.0
    else:
        raise ValueError(f"Unknown convention: {convention}. Use ACT/360, ACT/365, or 30/360.")


def term_to_years(term: str) -> float:
    """Convert a term string like '1D', '3M', '2Y', '18 MO', '1 WK' to year fraction."""
    t = str(term).strip().upper().replace(' ', '')
    if t.endswith('DY') or t.endswith('D'):
        num = t.replace('DY', '').replace('D', '')
        return int(num) / 360.0
    if t.endswith('WK') or t.endswith('W'):
        num = t.replace('WK', '').replace('W', '')
        return int(num) * 7 / 360.0
    if t.endswith('MO') or t.endswith('M'):
        num = t.replace('MO', '').replace('M', '')
        return int(num) / 12.0
    if t.endswith('YR') or t.endswith('Y'):
        num = t.replace('YR', '').replace('Y', '')
        return float(num)
    raise ValueError(f"Unknown term format: {term}")


def safe_log(x: np.ndarray, floor: float = 1e-10) -> np.ndarray:
    """Log with floor to avoid log(0). Used in LMM drift computations."""
    return np.log(np.maximum(x, floor))
