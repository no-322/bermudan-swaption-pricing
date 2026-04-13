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
    pass


def safe_log(x: np.ndarray, floor: float = 1e-10) -> np.ndarray:
    """Log with floor to avoid log(0). Used in LMM drift computations."""
    return np.log(np.maximum(x, floor))