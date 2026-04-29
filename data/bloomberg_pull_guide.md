# Bloomberg Data Pull Guide — Bermudan Swaption Backtest

## Overview

Pull data for **6 historical dates** to capture different rate/vol regimes:

| Date | Why this date |
|------|---------------|
| 2025-06-18 | ~1 year ago baseline |
| 2025-09-17 | Post-summer, pre-Fed Sept meeting |
| 2025-12-17 | Year-end, typically lower liquidity/wider spreads |
| 2026-01-15 | New year, fresh positioning |
| 2026-02-18 | Recent history |
| 2026-03-18 | Your current valuation date (already have this) |

For each date, you need 4 screenshots. Repeat the full process below for each date.

---

## Pull 1: SOFR OIS Swap Rates (for curve construction)

**Screen:** `ICVS`

1. Type `ICVS` → Enter
2. In the top-left, set **Currency** = `USD`
3. Set **Curve** = `S490 (USD SOFR OIS)`
4. Click the **Date** field (top-right) → enter the historical date (e.g., `06/18/2025`)
5. Make sure the display shows **swap rates** (not discount factors)
6. You need rates for these tenors visible: **1D, 1W, 1M, 2M, 3M, 6M, 9M, 1Y, 18M, 2Y, 3Y, 4Y, 5Y, 7Y, 10Y, 12Y, 15Y, 20Y, 25Y, 30Y, 40Y, 50Y**
7. Screenshot the full table

**What you're capturing:** Bid/Ask swap rates at each tenor — this rebuilds the discount curve.

---

## Pull 2: SOFR Futures Prices (for front-end curve)

**Screen:** `CT` (Contract Table)

1. Type `SFRA Comdty` → Enter → then `CT` → Enter
2. This shows all SOFR futures contracts
3. Click **Settings/Options** → set **Date** to the historical date
4. You need: **Contract name, Last/Settlement Price, Implied Rate** for all active contracts
5. Screenshot the full table (should show contracts from nearest month through ~3 years out)

**Alternative if CT doesn't backdate well:**

1. Type `SFRA Comdty` → Enter
2. Type `HP` → Enter (Historical Pricing)
3. Set the date to a single day (e.g., `06/18/2025` to `06/18/2025`)
4. Repeat for each active contract on that date: `SFRM5`, `SFRU5`, `SFRZ5`, `SFRH6`, `SFRM6`, `SFRU6`, `SFRZ6`, `SFRH7`, `SFRM7`, `SFRU7`, `SFRZ7`

This is tedious — if CT backdates, use that instead. One screenshot per date.

---

## Pull 3: Swaption Vol Surface — ATM (for SABR calibration)

**Screen:** `VCUB`

1. Type `VCUB` → Enter
2. Set parameters at the top:
   - **Currency:** `USD`
   - **Type:** `Payer` (or leave default, ATM is symmetric)
   - **Vol Type:** `Normal` (Bachelier) — NOT lognormal
   - **Strike:** `ATM`
   - **Date:** Enter the historical date (e.g., `06/18/2025`)
3. The grid should show:
   - **Rows (Expiry):** 1M, 3M, 6M, 9M, 1Y, 2Y, 3Y, 4Y, 5Y, 6Y, 7Y, 8Y, 9Y, 10Y, 12Y, 15Y, 20Y, 25Y, 30Y
   - **Columns (Tenor):** 1Y, 2Y, 3Y, 4Y, 5Y, 7Y, 10Y, 12Y, 15Y, 20Y, 25Y, 30Y
4. Screenshot the full grid

**Then repeat for smile strikes — change ONLY the Strike field each time:**

| Screenshot | Strike setting |
|------------|---------------|
| 3a | `ATM` |
| 3b | `ATM - 200` (i.e., -200bp) |
| 3c | `ATM - 100` |
| 3d | `ATM - 50` |
| 3e | `ATM - 25` |
| 3f | `ATM + 25` |
| 3g | `ATM + 50` |
| 3h | `ATM + 100` |
| 3i | `ATM + 200` |

That's **9 screenshots per date** for the vol surface. This gives you 9 strike points per (expiry, tenor) pair for SABR calibration.

**Important:** If VCUB shows the strike offset field differently, look for a dropdown or input box near the top that says "Spread" or "Offset" — enter the bp offset there (e.g., `-200`, `-100`, `-50`, `-25`, `0`, `+25`, `+50`, `+100`, `+200`).

---

## Pull 4: SWPM Bermudan Benchmark Price (dealer model price)

**Screen:** `SWPM`

1. Type `SWPM` → Enter
2. Set up the **10nc1 Payer Bermudan**:
   - **Product Type:** `Swaption`
   - **Swaption Style:** `Bermudan`
   - **Direction:** `Long Payer` (you pay fixed, receive float)
   - **Notional:** `10,000,000 USD`
   - **Underlying Swap Tenor:** `10Y`
   - **First Exercise:** `1Y` from the valuation date
   - **Exercise Frequency:** `Annual` (this gives you 9 exercise dates: 1Y, 2Y, ..., 9Y)
   - **Strike:** `ATM` (let Bloomberg compute it — note down the ATM strike it shows)
   - **Float Index:** `SOFR`
   - **Fixed Leg Freq:** `Semi-Annual` or `Annual` (use Semi-Annual for USD standard)
   - **Day Count:** `ACT/360` for float, `30/360` for fixed
3. Set the **Valuation Date / Curve Date** to the historical date (e.g., `06/18/2025`)
   - Look for a "Curves" or "Settings" tab → change the **As-Of Date**
4. Under **Model**, make sure it says `Hull-White 1-Factor` and `Normal` vol
5. Screenshot the **main pricing page** showing:
   - NPV
   - ATM Strike
   - DV01
   - Gamma
   - Vega
   - Theta
6. Also screenshot the **Exercise Schedule** tab if visible (shows exercise dates and probabilities)

**Then repeat with a European for comparison:**

7. Change **Swaption Style** from `Bermudan` to `European`
8. Set **Expiry** = `1Y`, **Swap Tenor** = `9Y` (this is the 1Yx9Y European — the first exercise of the 10nc1)
9. Keep the **same strike** as the Bermudan ATM strike you noted
10. Screenshot the European price

This gives you the **market-implied Bermudan premium** = SWPM Bermudan NPV - SWPM European NPV.

---

## Pull 5: European Swaption Market Prices (model validation)

Your model prices Europeans analytically (Bachelier). VCUB quotes are the **market price**. If your model matches VCUB, the curve + SABR calibration is validated. Pull explicit European prices for the co-terminal swaptions that define the 10nc1 exercise boundary.

**Screen:** `SWPM`

For each date, price these **7 co-terminal European payer swaptions** (all share the same final swap maturity):

| Swaption | Expiry | Swap Tenor | Notes |
|----------|--------|------------|-------|
| 1Yx9Y | 1Y | 9Y | First exercise of the 10nc1 |
| 2Yx8Y | 2Y | 8Y | Second exercise |
| 3Yx7Y | 3Y | 7Y | Third exercise |
| 5Yx5Y | 5Y | 5Y | Mid-point |
| 7Yx3Y | 7Y | 3Y | Late exercise |
| 9Yx1Y | 9Y | 1Y | Last exercise |
| 10Y (cap) | 10Y | 10Y | Upper bound reference |

For each one:
1. In `SWPM`, set **Swaption Style** = `European`
2. Set **Expiry** and **Swap Tenor** per the table above
3. Set **Strike** = `ATM`
4. Set **Direction** = `Long Payer`
5. Set **Vol Type** = `Normal`
6. Set **Valuation Date** = the historical date
7. Note down: **NPV, ATM Strike, Normal Vol (bps), Annuity, Forward Swap Rate**
8. One screenshot per swaption, or if they fit on one screen, batch them

**Why this matters:**
- Your Bachelier formula gives: Price = Annuity × [（F-K)Φ(d) + σ√T φ(d)]
- SWPM gives the market price using the same VCUB vols
- If your European prices match SWPM within ~1-2%, your curve and vol calibration are correct
- The Bermudan premium on top of that is then purely about the LSM exercise boundary — a much tighter validation problem

**Shortcut:** If screenshotting 7 swaptions per date is too many, just do **1Yx9Y, 5Yx5Y, and 9Yx1Y** (3 points spanning the exercise window).

---

## Pull 6: BVAL Bermudan Valuation (market consensus price)

**Screen:** `SWPM` (same 10nc1 Bermudan from Pull 4)

1. With the 10nc1 Bermudan already set up, look for a **BVAL** tab or **Pricing Source** dropdown
2. Switch pricing source from `Model` to `BVAL` if available
3. BVAL aggregates dealer contributed prices — this is the closest to a real market price
4. Screenshot showing the BVAL NPV alongside the HW1F model NPV
5. If BVAL is not available for this structure, note that — it means the structure is too bespoke for contributed pricing

**Note:** BVAL availability varies. It's more likely to exist for standard tenors (5nc1, 10nc1) than exotic structures. If it's not there, the European validation from Pull 5 is your primary validation.

---

## Summary: Screenshots Per Date

| # | Screen | What | Count |
|---|--------|------|-------|
| 1 | ICVS | SOFR OIS swap rates | 1 |
| 2 | CT/HP | SOFR futures | 1 |
| 3a-3i | VCUB | Vol surface at 9 strikes | 9 |
| 4a | SWPM | 10nc1 Bermudan payer (HW1F) | 1 |
| 5a-5c | SWPM | Co-terminal Europeans (1Yx9Y, 5Yx5Y, 9Yx1Y) | 3 |
| 6 | SWPM | BVAL Bermudan price (if available) | 1 |
| | | **Total per date** | **16** |

**Across 5 historical dates** (you already have 2026-03-18): **80 screenshots total**

---

## File Naming Convention

Save screenshots as:

```
data/backtest/YYYY-MM-DD_icvs.png
data/backtest/YYYY-MM-DD_futures.png
data/backtest/YYYY-MM-DD_vcub_atm.png
data/backtest/YYYY-MM-DD_vcub_minus200.png
data/backtest/YYYY-MM-DD_vcub_minus100.png
data/backtest/YYYY-MM-DD_vcub_minus50.png
data/backtest/YYYY-MM-DD_vcub_minus25.png
data/backtest/YYYY-MM-DD_vcub_plus25.png
data/backtest/YYYY-MM-DD_vcub_plus50.png
data/backtest/YYYY-MM-DD_vcub_plus100.png
data/backtest/YYYY-MM-DD_vcub_plus200.png
data/backtest/YYYY-MM-DD_swpm_bermudan.png
data/backtest/YYYY-MM-DD_swpm_euro_1Yx9Y.png
data/backtest/YYYY-MM-DD_swpm_euro_5Yx5Y.png
data/backtest/YYYY-MM-DD_swpm_euro_9Yx1Y.png
data/backtest/YYYY-MM-DD_swpm_bval.png
```

---

## After You Pull Everything

Bring the screenshots back here and I'll:
1. Read each one and transcribe the data into CSVs
2. Drop them into `data/backtest/` organized by date
3. Build the backtest pipeline that re-runs the full pricing stack per date
