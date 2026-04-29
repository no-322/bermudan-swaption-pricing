import numpy as np
from scipy.stats import norm
from src.curve import DiscountCurve


def payer_swap_npv(forwards_at_Tk: np.ndarray,
                    tenor_dates: np.ndarray,
                    k: int,
                    K: float) -> np.ndarray:
    """NPV of a payer swap starting at T_k, from simulated forwards at time T_k.

    Parameters
    ----------
    forwards_at_Tk : array shape (n_paths, N) — forward rates at exercise time
    tenor_dates    : array shape (N+1,) — tenor structure
    k              : exercise index (swap starts at T_k)
    K              : fixed strike rate (decimal)

    Returns
    -------
    array shape (n_paths,) — swap NPV per path (positive = payer swap in the money)
    """
    N = len(tenor_dates) - 1
    n_paths = forwards_at_Tk.shape[0]
    npv = np.zeros(n_paths)

    # Build path-dependent discount factors from T_k to each payment date
    # DF_path(T_k, T_{j+1}) = prod_{i=k}^{j} 1/(1 + delta_i * F_i(T_k))
    for j in range(k, N):
        delta_j = tenor_dates[j + 1] - tenor_dates[j]
        F_j = forwards_at_Tk[:, j]

        # Discount factor from T_k to T_{j+1}
        df_path = np.ones(n_paths)
        for i in range(k, j + 1):
            delta_i = tenor_dates[i + 1] - tenor_dates[i]
            F_i = forwards_at_Tk[:, i]
            df_path /= (1.0 + delta_i * F_i)

        # Cashflow at T_{j+1}: delta_j * (F_j - K)
        npv += delta_j * df_path * (F_j - K)

    return npv


def _swap_rate_at_Tk(forwards_at_Tk: np.ndarray,
                      tenor_dates: np.ndarray,
                      k: int) -> np.ndarray:
    """Compute the par swap rate at exercise date T_k from simulated forwards.

    S_k = (1 - DF(T_k, T_N)) / annuity
    where annuity = sum_{j=k}^{N-1} delta_j * DF(T_k, T_{j+1})

    Returns
    -------
    array shape (n_paths,)
    """
    N = len(tenor_dates) - 1
    n_paths = forwards_at_Tk.shape[0]

    annuity = np.zeros(n_paths)
    df_path = np.ones(n_paths)

    for j in range(k, N):
        delta_j = tenor_dates[j + 1] - tenor_dates[j]
        F_j = forwards_at_Tk[:, j]
        df_path /= (1.0 + delta_j * F_j)
        annuity += delta_j * df_path

    # par swap rate
    df_TN = df_path  # this is DF(T_k, T_N) after the loop
    swap_rate = np.where(annuity > 0, (1.0 - df_TN) / annuity, 0.0)
    return swap_rate


def longstaff_schwartz_bermudan(simulation: dict,
                                  curve: DiscountCurve,
                                  K: float,
                                  exercise_indices: np.ndarray,
                                  basis_degree: int = 3,
                                  itm_only: bool = True) -> dict:
    """Price a Bermudan payer swaption via Longstaff-Schwartz LSMC.

    Parameters
    ----------
    simulation       : dict from simulate_lmm()
    curve            : DiscountCurve for t=0 discounting
    K                : strike rate (decimal)
    exercise_indices : array of ints — indices into tenor_dates where exercise is allowed
    basis_degree     : polynomial degree for continuation value regression
    itm_only         : regress only on ITM paths (standard LS approach)

    Returns
    -------
    dict with price, std_error, exercise_probs, european_price, bermudan_premium
    """
    forwards = simulation['forwards']       # (n_paths, n_steps+1, N)
    timesteps = simulation['timesteps']     # (n_steps+1,)
    tenor_dates = simulation['tenor_dates'] # (N+1,)

    n_paths = forwards.shape[0]
    N = len(tenor_dates) - 1
    exercise_indices = np.asarray(exercise_indices)
    n_exercise = len(exercise_indices)

    # Find the time-step index closest to each exercise date
    def _find_step(T_target):
        return np.argmin(np.abs(timesteps - T_target))

    exercise_steps = np.array([_find_step(tenor_dates[k]) for k in exercise_indices])

    # ── Compute intrinsic values at each exercise date ────────────────────
    # IV[ex, :] = payer swap NPV at exercise date ex
    IV = np.zeros((n_exercise, n_paths))
    swap_rates = np.zeros((n_exercise, n_paths))

    for idx, k in enumerate(exercise_indices):
        step = exercise_steps[idx]
        fwd_at_k = forwards[:, step, :]  # (n_paths, N)
        IV[idx, :] = payer_swap_npv(fwd_at_k, tenor_dates, k, K)
        swap_rates[idx, :] = _swap_rate_at_Tk(fwd_at_k, tenor_dates, k)

    # ── Backward induction (Longstaff-Schwartz) ──────────────────────────

    # cashflow[m] = the (undiscounted-to-exercise-date) payoff that path m receives
    # exercise_time[m] = the exercise index at which path m exercises (-1 = never)
    cashflow = np.zeros(n_paths)
    exercise_time = np.full(n_paths, -1, dtype=int)

    # Start at the last exercise date
    last_idx = n_exercise - 1
    last_k = exercise_indices[last_idx]
    cashflow[:] = np.maximum(IV[last_idx, :], 0.0)
    exercise_time[cashflow > 0] = last_idx

    # Walk backwards
    for ex_idx in range(n_exercise - 2, -1, -1):
        k = exercise_indices[ex_idx]
        step_k = exercise_steps[ex_idx]
        iv_k = IV[ex_idx, :]

        # Discount cashflows from the next exercise date to this one
        # Use path-dependent discounting between T_k and the actual exercise time
        next_k = exercise_indices[ex_idx + 1]
        step_next = exercise_steps[ex_idx + 1]

        # Path-dependent DF from T_k to T_{next_k}
        fwd_at_k = forwards[:, step_k, :]
        df_k_to_next = np.ones(n_paths)
        for j in range(k, next_k):
            delta_j = tenor_dates[j + 1] - tenor_dates[j]
            F_j = fwd_at_k[:, j]
            df_k_to_next /= (1.0 + delta_j * F_j)

        # Discounted future cashflow (from perspective of T_k)
        # For paths that exercise later, we need to discount through all
        # intermediate periods. Simplified: discount the cashflow by
        # DF(T_k, T_{exercise_time})
        # But for LS, we just need the continuation value at T_k.
        # We'll use the one-step discount as an approximation for the regression.
        discounted_cf = cashflow * df_k_to_next

        # Identify ITM paths
        if itm_only:
            itm = iv_k > 0
        else:
            itm = np.ones(n_paths, dtype=bool)

        n_itm = np.sum(itm)
        if n_itm < basis_degree + 2:
            # Not enough ITM paths for regression, skip this exercise date
            continue

        # Build polynomial basis on swap rate
        S = swap_rates[ex_idx, itm]
        Y = discounted_cf[itm]

        # Polynomial basis: [1, S, S^2, ..., S^d]
        X = np.column_stack([S ** p for p in range(basis_degree + 1)])

        # OLS regression
        try:
            beta = np.linalg.lstsq(X, Y, rcond=None)[0]
        except np.linalg.LinAlgError:
            continue

        # Predicted continuation value for ALL ITM paths
        S_all = swap_rates[ex_idx, :]
        X_all = np.column_stack([S_all ** p for p in range(basis_degree + 1)])
        continuation = X_all @ beta

        # Exercise decision: exercise if IV > continuation AND ITM
        exercise_now = (iv_k > continuation) & (iv_k > 0)

        # Update cashflows and exercise times
        cashflow[exercise_now] = iv_k[exercise_now]
        exercise_time[exercise_now] = ex_idx

        # For paths not exercising now, keep the discounted future cashflow
        # (already stored from next iteration)

    # ── Discount all cashflows to t=0 ────────────────────────────────────
    # Use the curve discount factors (not path-dependent) for t=0 discounting
    # This is the standard approach: DF(0, T_k) from the initial curve
    pv = np.zeros(n_paths)
    for ex_idx in range(n_exercise):
        k = exercise_indices[ex_idx]
        T_k = tenor_dates[k]
        mask = exercise_time == ex_idx
        pv[mask] = cashflow[mask] * curve.df(T_k)

    bermudan_price = np.mean(pv)
    bermudan_se = np.std(pv) / np.sqrt(n_paths)

    # Exercise probabilities
    exercise_probs = np.array([np.mean(exercise_time == ex_idx)
                               for ex_idx in range(n_exercise)])

    # ── European price (exercise only at first date) ─────────────────────
    first_k = exercise_indices[0]
    T_first = tenor_dates[first_k]
    euro_pv = np.maximum(IV[0, :], 0.0) * curve.df(T_first)
    european_price = np.mean(euro_pv)

    return {
        'price': bermudan_price,
        'std_error': bermudan_se,
        'exercise_probs': exercise_probs,
        'european_price': european_price,
        'bermudan_premium': bermudan_price - european_price,
    }


def european_swaption_bachelier(curve: DiscountCurve,
                                 expiry: float,
                                 tenor: float,
                                 K: float,
                                 sigma_normal: float,
                                 payer: bool = True) -> float:
    """Analytical European swaption price under Bachelier (normal) model.

    Price = Annuity * [(F-K)*Phi(d) + sigma*sqrt(T)*phi(d)]
    where d = (F-K) / (sigma*sqrt(T))
    """
    F = curve.par_swap_rate(expiry, tenor, freq=0.5)
    ann = curve.annuity(expiry, tenor, freq=0.5)
    sqrt_T = np.sqrt(expiry)

    if sigma_normal <= 0 or sqrt_T <= 0:
        return max(0, ann * (F - K)) if payer else max(0, ann * (K - F))

    d = (F - K) / (sigma_normal * sqrt_T)

    if payer:
        price = ann * ((F - K) * norm.cdf(d) + sigma_normal * sqrt_T * norm.pdf(d))
    else:
        price = ann * ((K - F) * norm.cdf(-d) + sigma_normal * sqrt_T * norm.pdf(d))

    return max(0.0, price)
