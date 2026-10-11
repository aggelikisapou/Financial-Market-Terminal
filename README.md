# ⚡ Financial Market Terminal v2

A high-performance, single-file financial analytics dashboard built with Python and Streamlit. This terminal provides institutional-grade analytics, interactive charting, dynamic valuation modeling, robust risk metrics, and real-time news sentiment for any publicly traded company.

## 🚀 Key Features

- **Advanced Charting & Technicals:** Interactive candlestick and line charts equipped with toggleable linear/log scales. Includes indicators for Volume, 50/200-Day SMAs, EMA 20, VWAP, Bollinger Bands, MACD, ATR, and a 14-period RSI. Supports timeframes from 1-Day (intraday) to Max with clean, contiguous axes (no weekend/holiday gaps).
- **Synchronized DCF & Monte Carlo:** A live Discounted Cash Flow engine linked directly to a vectorized 10,000-iteration Monte Carlo simulation. Adjust WACC, Terminal Growth Rate (g), and Target Operating Margins via sliders or use preset scenarios ("Consensus Base", "Recession Shock", "Tech Boom") to see real-time recalculations.
- **Probabilistic Modeling Visualizations:** View Monte Carlo outputs as a Probability Density Bell Curve, a Sensitivity Tornado Diagram, a Geometric Brownian Motion (GBM) Spaghetti Plot, or a percentile Fan Chart.
- **Risk & Quality Screening:** A dedicated panel tracking institutional metrics including FCF yield, EV/FCF, ROIC vs WACC spread, Net Debt / EBITDA, Interest Coverage, Sloan Accrual Ratio, Historical/Parametric VaR (95%), and Max Drawdown.
- **Dynamic Peer Comparison:** Automatically routes the target ticker to relative industry competitors based on sector metadata, or input a custom comma-separated list of peers. Compare P/E, P/B, Operating Margins, and ROE in an interactive, clickable grid that lets you swap the active dashboard target instantly.
- **Institutional Excel Export:** Click to download a fully formatted, multi-sheet `.xlsx` file containing the tuned DCF assumptions, a 5-year FCF forecast schedule, terminal value breakdown, and a Bear/Base/Bull scenario analysis matrix.
- **Live News & Sentiment:** Fetches the latest 6 headlines for the target company using a robust RSS parser, automatically scoring the sentiment (Bullish, Bearish, or Neutral) of each headline using natural language processing.

## 🛠️ Installation & Setup

1. **Clone the repository:**
   `git clone https://github.com/YOUR_USERNAME/financial-market-terminal.git`
   `cd financial-market-terminal`

2. **Install Dependencies:**
   Requires Python 3.8+ and Streamlit 1.40+.
   `pip install streamlit>=1.40 yfinance plotly pandas numpy xlsxwriter textblob`

## 🖥️ Usage

1. Launch the app locally:
   `streamlit run Stock_Analytics_Dashboard_v2.py`
2. Access `http://localhost:8501` in your browser.
3. Enter any ticker symbol (e.g., `AAPL`, `NVDA`, `MSFT`) in the search bar.
4. Use the timeframe pills and chart overlays to review technical indicators across intraday or historical bars.
5. Expand the **Interactive DCF Valuation Assumptions** panel to adjust discount rates, operating margins, or apply preset macroeconomic scenarios.
6. Inspect the Monte Carlo distributions via Bell Curve, Sensitivity Tornado, Fan Chart, or GBM paths.
7. Click any competitor symbol in the **Interactive Peer Comparison** table to instantly pivot the terminal to that firm.
8. Export your adjusted model directly using **Export Live DCF Model to Excel**.

---

## 🗺️ Multi-Asset Expansion Roadmap

The architecture is currently expanding beyond equities into a unified cross-asset terminal:

### Phase 1: Commodities & Energy
- **Spot & Futures Coverage:** Track major energy (`CL=F`, `NG=F`), precious metals (`GC=F`, `SI=F`), and agricultural commodities.
- **Term Structure & Curve Analytics:** Futures forward curves, contango vs. backwardation visualization, and roll-yield metrics.
- **Macro Correlation Matrix:** Real-time correlation tracking between commodities and inflation expectations.

### Phase 2: Foreign Exchange & Global Currencies
- **G10 & Emerging Market Pairs:** Live FX pricing via `EURUSD=X`, `USDJPY=X`, `GBPUSD=X`, and currency cross matrices.
- **Macro Drivers:** Central bank policy rate differentials, purchasing power parity (PPP) indicators, and real effective exchange rate (REER) tracking.
- **FX Volatility Surface:** Implied volatility comparisons and currency risk indices.

### Phase 3: Fixed Income, Rates & Sovereign Debt
- **Yield Curve Engine:** Full US Treasury term structure (`^IRX`, `^FVX`, `^TNX`, `^TYX`) with 2Y/10Y and 3M/10Y spread monitors.
- **Curve Inversion Alerts:** Automatic detection and visual signaling for yield curve inversions and recession risk.
- **Credit & Duration Metrics:** Effective duration, convexity calculators, and corporate credit spread indices (Investment Grade vs. High Yield).

### Phase 4: Digital Assets & Cryptocurrencies
- **Tier-1 Crypto Coverage:** Real-time metrics for major pairs (`BTC-USD`, `ETH-USD`, `SOL-USD`).
- **On-Chain & Market Indicators:** Bitcoin dominance ratios, 24-hour volume profiles, and aggregate stablecoin liquidity flow.
- **Cross-Asset Beta:** Quantitative beta tracking comparing digital asset performance to tech equities and gold.

## ⚠️ Disclaimer
Data is sourced from Yahoo Finance via the unofficial `yfinance` library. Metrics may occasionally return `N/A` due to rate limiting or missing financial statement data. This tool is for informational and educational purposes only and does not constitute financial advice.
