# Financial Repression Monitor

A Streamlit dashboard that tracks macro indicators signaling proximity to a **financial repression** regime — where governments deliberately keep interest rates below inflation to erode the real value of public debt.

Live data is pulled automatically from **FRED** (Federal Reserve Bank of St. Louis) and **Yahoo Finance** on page load, with a 1-hour cache.

---

## Indicators tracked

| Indicator | Source | Threshold |
|---|---|---|
| Debt-to-GDP ratio | FRED: GFDEGDQ188S | > 100% = systemic repression |
| Fiscal deficit (% GDP) | Static / CBO | > 5% = repression likely |
| Net interest expense (% GDP) | Static / CBO | > 3.2% = all-time post-WWII high |
| Real interest rate (Fed funds − CPI) | FRED: FEDFUNDS, CPIAUCSL | < 0% = repression active |
| 10-yr TIPS real yield | FRED: DFII10 | < 0% = repression active |
| Fed independence (chair succession) | Event-based | May 2026 |
| SLR reform / structural tools | Event-based | Ongoing |
| Market pricing (breakevens, HY spreads) | FRED: T10YIE, BAMLH0A0HYM2 | Breakeven > 3% = alert |

---

## Run locally

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/repression-monitor.git
cd repression-monitor

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Set FRED API key for higher rate limits
#    Free key at: https://fred.stlouisfed.org/docs/api/api_key.html
export FRED_API_KEY=your_key_here

# 4. Run
streamlit run app.py
```

---

## Deploy to Streamlit Cloud (free)

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in
3. Click **New app** → select your repo → set main file to `app.py`
4. (Optional) Add `FRED_API_KEY` under **Advanced settings → Secrets**:
   ```toml
   FRED_API_KEY = "your_key_here"
   ```
5. Click **Deploy** — live in ~60 seconds

---

## File structure

```
repression-monitor/
├── app.py            # Streamlit UI
├── data_fetcher.py   # FRED + Yahoo Finance data pulls
├── indicators.py     # Scoring logic, watchlist, catalyst data
├── requirements.txt  # Python dependencies
└── README.md
```

---

## Data sources

- **FRED** (Federal Reserve Bank of St. Louis) — DFII10, DGS10, T10YIE, FEDFUNDS, CPIAUCSL, BAMLH0A0HYM2, GFDEGDQ188S
- **Yahoo Finance** (via yfinance) — KRE (regional bank ETF), ^TNX (10-yr yield)
- **CBO** Budget & Economic Outlook (static values for deficit and interest expense)
- **IMF** World Economic Outlook (static debt-to-GDP trajectory)

---

*Educational research only — not investment advice.*
