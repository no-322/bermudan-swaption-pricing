"""Compute trading strategy signals and P&L from backtest results."""
import numpy as np
import pandas as pd
import json
import os
from datetime import date
from src.curve import DiscountCurve

with open('data/backtest_results.json') as f:
    bt = json.load(f)

dates_sorted = sorted(bt.keys())

# Compute premium ratios and market regime
regime = []
for d in dates_sorted:
    r = bt[d]
    prem_ratio = r['premium'] / r['european_bachelier'] * 100

    # Get 2s10s slope
    base = f'data/backtest/{d}/'
    if d == '2026-03-18':
        zero_df = pd.read_csv('data/sofr_zero_curve.csv')
        curve = DiscountCurve.from_zero_curve(date(2026, 3, 18), zero_df)
    else:
        sr_path = base + 'swap_rates.csv'
        if os.path.exists(sr_path):
            sr = pd.read_csv(sr_path)
            if 'bid' in sr.columns:
                sr['mid'] = (sr['bid'] + sr['ask']) / 2.0
            curve = DiscountCurve.from_market_data(
                date(int(d[:4]), int(d[5:7]), int(d[8:10])), sr)
        else:
            continue

    r2 = curve.par_swap_rate(0, 2, freq=0.5) * 100
    r10 = curve.par_swap_rate(0, 10, freq=0.5) * 100
    slope = r10 - r2

    regime.append({
        'date': d,
        'atm_strike': r['atm_strike'],
        'bermudan': r['bermudan'],
        'european': r['european_bachelier'],
        'premium': r['premium'],
        'prem_ratio': prem_ratio,
        'rate_2y': r2,
        'rate_10y': r10,
        'slope_2s10s': slope,
    })

df = pd.DataFrame(regime)
mean_ratio = df['prem_ratio'].mean()

print('=== PREMIUM RATIO BY DATE ===')
print(df[['date', 'prem_ratio', 'slope_2s10s', 'premium']].to_string(index=False))
print(f'\nMean ratio: {mean_ratio:.1f}%  Std: {df["prem_ratio"].std():.1f}%')

# Correlations
print('\n=== CORRELATIONS WITH PREMIUM RATIO ===')
for col in ['rate_2y', 'slope_2s10s']:
    print(f'  {col}: {df["prem_ratio"].corr(df[col]):.3f}')

# Strategy 1: Premium Rich/Cheap
print('\n=== STRATEGY 1: PREMIUM RICH/CHEAP ===')
total_pnl = 0
wins = 0
for i in range(len(df) - 1):
    d1 = df.iloc[i]
    d2 = df.iloc[i + 1]
    signal = d1['prem_ratio'] - mean_ratio

    if signal < 0:
        position = 'LONG'
        pnl = d2['premium'] - d1['premium']
    else:
        position = 'SHORT'
        pnl = d1['premium'] - d2['premium']

    total_pnl += pnl
    if pnl > 0:
        wins += 1

    print(f'{d1["date"]} -> {d2["date"]}: {position} (signal={signal:+.1f}%)  P&L=${pnl:+,.0f}')

n_trades = len(df) - 1
print(f'\nTotal P&L: ${total_pnl:+,.0f}')
print(f'Win rate: {wins}/{n_trades} ({wins/n_trades*100:.0f}%)')

# Strategy 2: Model vs Dealer
print('\n=== STRATEGY 2: MODEL vs DEALER (2026-03-18) ===')
our_prem = bt['2026-03-18']['premium']
our_euro = bt['2026-03-18']['european_bachelier']
our_ratio = our_prem / our_euro * 100

bbg_berm = 235822.51
bbg_euro = 154874.33
bbg_prem = bbg_berm - bbg_euro
bbg_ratio = bbg_prem / bbg_euro * 100

print(f'Our premium ratio:  {our_ratio:.1f}%')
print(f'BBG premium ratio:  {bbg_ratio:.1f}%')
print(f'Gap:                {bbg_ratio - our_ratio:.1f}%')
print(f'Spread per $10MM:   ${bbg_prem - our_prem:,.0f}')
