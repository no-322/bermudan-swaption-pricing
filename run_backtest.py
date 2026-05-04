"""Run pricing pipeline across all 6 historical dates."""
import numpy as np
import pandas as pd
import json
import os
from datetime import date
from src.curve import DiscountCurve
from src.sabr import calibrate_full_surface, hagan_normal_vol
from src.lmm import simulate_lmm
from src.pricer import longstaff_schwartz_bermudan, european_swaption_bachelier

backtest_dates = {
    '2025-03-18': date(2025, 3, 18),
    '2025-06-18': date(2025, 6, 18),
    '2025-09-18': date(2025, 9, 18),
    '2025-12-18': date(2025, 12, 18),
    '2026-02-18': date(2026, 2, 18),
    '2026-03-18': date(2026, 3, 18),
}

exp_map = {
    '1Mo': 1/12, '3Mo': 3/12, '6Mo': 6/12, '9Mo': 9/12,
    '1Yr': 1, '2Yr': 2, '3Yr': 3, '4Yr': 4, '5Yr': 5,
    '6Yr': 6, '7Yr': 7, '8Yr': 8, '9Yr': 9, '10Yr': 10,
}
ten_map = {'1Y': 1, '2Y': 2, '3Y': 3, '4Y': 4, '5Y': 5, '7Y': 7, '10Y': 10}
offset_files = {
    -200: 'vcub_minus200.csv', -100: 'vcub_minus100.csv',
    -50: 'vcub_minus50.csv', -25: 'vcub_minus25.csv',
    0: 'vcub_atm.csv',
    25: 'vcub_plus25.csv', 50: 'vcub_plus50.csv',
    100: 'vcub_plus100.csv', 200: 'vcub_plus200.csv',
}
tenor_structure = np.arange(0, 7, dtype=float)
exercise_indices = np.array([1, 2, 3, 4, 5])

all_results = {}

for date_str, pricing_date in backtest_dates.items():
    print(f'=== {date_str} ===')
    base = f'data/backtest/{date_str}/'

    # Build curve
    if date_str == '2026-03-18':
        zero_df = pd.read_csv('data/sofr_zero_curve.csv')
        curve = DiscountCurve.from_zero_curve(pricing_date, zero_df)
    else:
        sr_path = base + 'swap_rates.csv'
        if not os.path.exists(sr_path):
            print('  SKIP - no swap_rates.csv')
            continue
        sr = pd.read_csv(sr_path)
        if 'bid' in sr.columns and 'ask' in sr.columns:
            sr['mid'] = (sr['bid'] + sr['ask']) / 2.0
        try:
            curve = DiscountCurve.from_market_data(pricing_date, sr)
        except Exception as e:
            print(f'  SKIP - curve failed: {e}')
            continue

    K = curve.par_swap_rate(1.0, 5.0, freq=0.5)
    print(f'  ATM strike: {K*100:.4f}%')

    # Load vol cube
    rows = []
    n_loaded = 0
    for off_bp, fname in offset_files.items():
        fpath = base + fname
        if not os.path.exists(fpath):
            continue
        try:
            df = pd.read_csv(fpath, index_col=0)
            n_loaded += 1
        except Exception:
            continue
        for el, te in exp_map.items():
            for tl, tt in ten_map.items():
                if el in df.index and tl in df.columns:
                    v = df.loc[el, tl]
                    if pd.notna(v) and v > 0:
                        rows.append({'expiry_years': te, 'tenor_years': tt,
                                     'strike_offset': off_bp / 10000.0, 'market_vol': v / 10000.0})

    if not rows:
        print('  SKIP - no vol data')
        continue

    vol_cube = pd.DataFrame(rows)
    sabr_params = calibrate_full_surface(curve, vol_cube, beta=0.5)
    n_ok = sabr_params['success'].sum()
    print(f'  SABR: {n_ok}/{len(sabr_params)}, RMSE={sabr_params["rmse"].mean()*10000:.2f}bp')

    # LMM + LSMC
    sim = simulate_lmm(curve, sabr_params, tenor_structure,
                        n_paths=50000, dt=0.25, correlation_lambda=0.05,
                        seed=42, antithetic=True)
    result = longstaff_schwartz_bermudan(sim, curve, K, exercise_indices,
                                          basis_degree=3, itm_only=True)

    # Bachelier European
    euro_bach = result['european_price']
    if (1.0, 5.0) in sabr_params.index:
        row = sabr_params.loc[(1.0, 5.0)]
        sigma_N = hagan_normal_vol(row['F'], row['F'], 1.0,
                                    row['sigma0'], 0.5, row['rho'], row['nu'])
        euro_bach = european_swaption_bachelier(curve, 1.0, 5.0, K, sigma_N, payer=True)

    print(f'  Berm=${result["price"]*1e7:,.0f}  Euro=${euro_bach*1e7:,.0f}  Prem=${result["bermudan_premium"]*1e7:,.0f}')
    print(f'  Ex probs: {np.round(result["exercise_probs"], 3)}')

    all_results[date_str] = {
        'atm_strike': round(K * 100, 4),
        'bermudan': round(result['price'] * 1e7, 2),
        'std_error': round(result['std_error'] * 1e7, 2),
        'european_mc': round(result['european_price'] * 1e7, 2),
        'european_bachelier': round(euro_bach * 1e7, 2),
        'premium': round(result['bermudan_premium'] * 1e7, 2),
        'exercise_probs': [round(p, 4) for p in result['exercise_probs']],
        'sabr_pairs_ok': int(n_ok),
        'sabr_rmse_bp': round(sabr_params['rmse'].mean() * 10000, 2),
    }

with open('data/backtest_results.json', 'w') as f:
    json.dump(all_results, f, indent=2)
print('\nSaved to data/backtest_results.json')
