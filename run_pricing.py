"""Run the full pricing pipeline for the primary date (2026-03-18)."""
import numpy as np
import pandas as pd
from datetime import date
from src.curve import DiscountCurve
from src.sabr import calibrate_full_surface, hagan_normal_vol
from src.lmm import simulate_lmm
from src.pricer import longstaff_schwartz_bermudan, european_swaption_bachelier

# Stage 1: Curve
zero_df = pd.read_csv('data/sofr_zero_curve.csv')
curve = DiscountCurve.from_zero_curve(date(2026, 3, 18), zero_df)
K = curve.par_swap_rate(1.0, 5.0, freq=0.5)
print(f'ATM strike (1Yx5Y): {K*100:.4f}%')

# Stage 2: SABR
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
    for exp_lbl, T_exp in exp_map.items():
        for ten_lbl, T_ten in ten_map.items():
            if exp_lbl in df.index and ten_lbl in df.columns:
                vol = df.loc[exp_lbl, ten_lbl]
                if pd.notna(vol) and vol > 0:
                    rows.append({
                        'expiry_years': T_exp, 'tenor_years': T_ten,
                        'strike_offset': off_bp / 10000.0,
                        'market_vol': vol / 10000.0,
                    })

vol_cube = pd.DataFrame(rows)
sabr_params = calibrate_full_surface(curve, vol_cube, beta=0.5)
n_ok = sabr_params['success'].sum()
print(f'SABR: {n_ok}/{len(sabr_params)} calibrated, RMSE={sabr_params["rmse"].mean()*10000:.2f}bp')

# Stage 3 + 4: LMM and LSMC
tenor_structure = np.arange(0, 7, dtype=float)
exercise_indices = np.array([1, 2, 3, 4, 5])

print('Running LMM (100K paths)...')
sim = simulate_lmm(curve, sabr_params, tenor_structure,
                    n_paths=100000, dt=0.25, correlation_lambda=0.05,
                    seed=42, antithetic=True)

result = longstaff_schwartz_bermudan(sim, curve, K, exercise_indices,
                                      basis_degree=3, itm_only=True)

# Bachelier European
row = sabr_params.loc[(1.0, 5.0)]
sigma_N = hagan_normal_vol(row['F'], row['F'], 1.0,
                            row['sigma0'], 0.5, row['rho'], row['nu'])
euro_bach = european_swaption_bachelier(curve, 1.0, 5.0, K, sigma_N, payer=True)

print()
print('=== RESULTS ===')
print(f'Bermudan payer:    ${result["price"]*1e7:,.2f} +/- ${result["std_error"]*1e7:,.2f}')
print(f'European (MC):     ${result["european_price"]*1e7:,.2f}')
print(f'European (Bach):   ${euro_bach*1e7:,.2f}')
print(f'Bermudan premium:  ${result["bermudan_premium"]*1e7:,.2f}')
print(f'Exercise probs:    {np.round(result["exercise_probs"], 4)}')
print()
print(f'Bloomberg Berm:    $235,822.51')
print(f'Bloomberg Euro:    $154,874.33')
print(f'Gap:               {(result["price"]*1e7 - 235822.51)/235822.51*100:+.1f}%')
