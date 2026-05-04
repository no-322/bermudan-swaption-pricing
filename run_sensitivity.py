"""Run sensitivity analysis across 5 dimensions."""
import numpy as np
import pandas as pd
import json
from datetime import date
from src.curve import DiscountCurve
from src.sabr import calibrate_full_surface
from src.lmm import simulate_lmm
from src.pricer import longstaff_schwartz_bermudan

# Setup
zero_df = pd.read_csv('data/sofr_zero_curve.csv')
curve = DiscountCurve.from_zero_curve(date(2026, 3, 18), zero_df)

base = 'data/backtest/2026-03-18/'
offset_files = {
    -200: 'vcub_minus200.csv', -100: 'vcub_minus100.csv',
    -50: 'vcub_minus50.csv', -25: 'vcub_minus25.csv',
    0: 'vcub_atm.csv',
    25: 'vcub_plus25.csv', 50: 'vcub_plus50.csv',
    100: 'vcub_plus100.csv', 200: 'vcub_plus200.csv',
}
exp_map = {
    '1Mo': 1/12, '3Mo': 3/12, '6Mo': 6/12, '9Mo': 9/12,
    '1Yr': 1, '2Yr': 2, '3Yr': 3, '4Yr': 4, '5Yr': 5,
    '6Yr': 6, '7Yr': 7, '8Yr': 8, '9Yr': 9, '10Yr': 10,
}
ten_map = {'1Y': 1, '2Y': 2, '3Y': 3, '4Y': 4, '5Y': 5, '7Y': 7, '10Y': 10}

rows = []
for off_bp, fname in offset_files.items():
    try:
        df = pd.read_csv(base + fname, index_col=0)
    except FileNotFoundError:
        continue
    for el, te in exp_map.items():
        for tl, tt in ten_map.items():
            if el in df.index and tl in df.columns:
                v = df.loc[el, tl]
                if pd.notna(v) and v > 0:
                    rows.append({'expiry_years': te, 'tenor_years': tt,
                                 'strike_offset': off_bp / 10000.0, 'market_vol': v / 10000.0})

vol_cube_base = pd.DataFrame(rows)
sabr_base = calibrate_full_surface(curve, vol_cube_base, beta=0.5)
tenor_structure = np.arange(0, 7, dtype=float)
exercise_indices = np.array([1, 2, 3, 4, 5])


def run_pricing(crv, sabr_p, n_paths=30000, corr_lam=0.05, seed=42):
    sim = simulate_lmm(crv, sabr_p, tenor_structure, n_paths=n_paths,
                        dt=0.25, correlation_lambda=corr_lam, seed=seed, antithetic=True)
    strike = crv.par_swap_rate(1.0, 5.0, freq=0.5)
    return longstaff_schwartz_bermudan(sim, crv, strike, exercise_indices,
                                       basis_degree=3, itm_only=True)


results = {}

# Baseline
print('Baseline...')
r = run_pricing(curve, sabr_base)
results['baseline'] = {'bermudan': r['price']*1e7, 'european': r['european_price']*1e7,
                        'premium': r['bermudan_premium']*1e7,
                        'exercise_probs': r['exercise_probs'].tolist()}
print(f'  Berm=${r["price"]*1e7:,.0f}  Prem=${r["bermudan_premium"]*1e7:,.0f}')

# (1) Correlation
print('\n(1) Correlation...')
for lam in [0.02, 0.05, 0.10]:
    r = run_pricing(curve, sabr_base, corr_lam=lam)
    results[f'lambda={lam}'] = {'bermudan': r['price']*1e7, 'european': r['european_price']*1e7,
                                 'premium': r['bermudan_premium']*1e7}
    print(f'  lam={lam}: Berm=${r["price"]*1e7:,.0f}  Prem=${r["bermudan_premium"]*1e7:,.0f}')

# (2) Vol shift
print('\n(2) Vol shift...')
for shift in [-5, 0, 5]:
    vc = vol_cube_base.copy()
    vc['market_vol'] = vc['market_vol'] + shift / 10000.0
    sp = calibrate_full_surface(curve, vc, beta=0.5)
    r = run_pricing(curve, sp)
    results[f'vol_shift={shift:+d}bp'] = {'bermudan': r['price']*1e7, 'european': r['european_price']*1e7,
                                           'premium': r['bermudan_premium']*1e7}
    print(f'  {shift:+d}bp: Berm=${r["price"]*1e7:,.0f}  Prem=${r["bermudan_premium"]*1e7:,.0f}')

# (3) Curve shape
print('\n(3) Curve shape...')
scenarios = {
    'parallel +50bp': lambda t, z: z + 0.005,
    'parallel -50bp': lambda t, z: z - 0.005,
    'bear steepener': lambda t, z: z + 0.0025 + 0.005 * (t / max(t.max(), 1)),
    'bull flattener': lambda t, z: z - 0.0075 + 0.005 * (t / max(t.max(), 1)),
}
for name, fn in scenarios.items():
    Z_shifted = np.maximum(fn(curve.pillar_times, curve.zero_rates), 0.001)
    crv = DiscountCurve(curve.pricing_date, curve.pillar_times.copy(), Z_shifted)
    sp = calibrate_full_surface(crv, vol_cube_base, beta=0.5)
    r = run_pricing(crv, sp)
    K_s = crv.par_swap_rate(1.0, 5.0, freq=0.5)
    results[name] = {'bermudan': r['price']*1e7, 'european': r['european_price']*1e7,
                      'premium': r['bermudan_premium']*1e7, 'atm_strike': K_s*100}
    print(f'  {name}: Berm=${r["price"]*1e7:,.0f}  Prem=${r["bermudan_premium"]*1e7:,.0f}')

# (4) SABR rho
print('\n(4) SABR rho...')
for rho_shift in [-0.1, 0, 0.1]:
    sp = sabr_base.copy()
    sp['rho'] = np.clip(sp['rho'] + rho_shift, -0.999, 0.999)
    r = run_pricing(curve, sp)
    results[f'rho_shift={rho_shift:+.1f}'] = {'bermudan': r['price']*1e7, 'european': r['european_price']*1e7,
                                                'premium': r['bermudan_premium']*1e7}
    print(f'  rho {rho_shift:+.1f}: Berm=${r["price"]*1e7:,.0f}  Prem=${r["bermudan_premium"]*1e7:,.0f}')

# (5) Convergence
print('\n(5) Convergence...')
for n in [1000, 5000, 10000, 30000, 50000, 100000]:
    r = run_pricing(curve, sabr_base, n_paths=n)
    results[f'paths={n}'] = {'bermudan': r['price']*1e7, 'std_error': r['std_error']*1e7}
    print(f'  {n:>6d}: Berm=${r["price"]*1e7:,.0f} +/- ${r["std_error"]*1e7:,.0f}')

with open('data/sensitivity_results.json', 'w') as f:
    json.dump(results, f, indent=2)
print('\nSaved to data/sensitivity_results.json')
