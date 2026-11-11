# Upbit KRW read-only monitor

Free GitHub Actions hourly **data collector**, not a trading bot. It never authenticates to an exchange, places orders, accesses wallets, or sends notifications. No API key is required. Results are downloadable from each GitHub Actions run as an artifact (`snapshot.json`, `markets.csv`, `report.md`). This does **not** automatically connect to ChatGPT or its scheduled monitoring; that integration requires a separate verified step.

## Setup
1. Create a public GitHub repository (avoid secrets/personal data in public code or artifacts).
2. Upload `monitor.py`, `README.md` and `.github/workflows/monitor.yml` preserving the full path. GitHub web upload may not preserve dotfolders reliably; use **Add file → Create new file** and type `.github/workflows/monitor.yml` into the filename field, then paste the workflow contents if necessary.
3. Open **Actions → Upbit read-only hourly snapshot → Run workflow**.
4. Wait for the run and download its **Artifacts** ZIP. Inspect `report.md`, `markets.csv`, `snapshot.json`.
5. Scheduled run: every hour at minute 15 **UTC**, which is minute 15 KST as well. GitHub schedule is best-effort and may be delayed or skipped. Inactivity may disable schedules after 60 days in a public repository.

## How screening works
All KRW markets: 24h signed change, turnover, high/low from Upbit `/ticker`; up to 25 hourly candles per market. Compare the last completed 60m candle turnover with the median of 6 preceding hourly candles; calculate 14-period simple RSI and candle close location. Observation candidates have 24h rise 3–12%, hour turnover ratio >=1.5, green completed candle, close position >=0.65, 24h turnover >=1 billion KRW and RSI <70. Theme tags are limited manual categories and not proof of leadership. **Never interpret shortlist as A/B+ buy recommendations.** Support/stop/targets, actual orderbook liquidity, market regime, trade risk/reward, and theme-leader verification are not automated.

## Safety & costs
- Uses public market data only. No exchange API keys, no payment info, no private credentials, no order endpoints.
- Workflow token is read-only; results stored as short-lived GitHub Actions artifacts, not committed back into the public repository.
- Public repo standard hosted Actions is generally free under GitHub's public-repository policy. Keep your $0 spending budgets and check billing after the first run.
- API failures retry up to four times after the first attempt, with 2/5/10/20s delays. An incomplete scan exits with an error and is not a market NO TRADE decision.
- Personal holdings are intentionally omitted from this public repository.
