# ⚡ Financial Market Terminal

A comprehensive, single-page financial dashboard built with Python and Streamlit. This terminal provides institutional-grade analytics, interactive charting, dynamic valuation modeling, and real-time news sentiment for any publicly traded company. 

## Key Features

* **Advanced Charting & Technicals:** Interactive candlestick charts equipped with Volume overlays, 50/200-Day SMAs, Bollinger Bands, and a 14-period RSI indicator. Supports timeframes from 1-Day (intraday) to Max.
* **Interactive DCF Valuation:** A live Discounted Cash Flow engine. Adjust WACC, Terminal Growth Rate (g), and Target Operating Margins via sliders to see real-time recalculations of intrinsic value and implied upside/downside.
* **Monte Carlo & Probabilistic Modeling:** Runs 10,000 simulations on valuation parameters. View the output as a Probability Density Bell Curve, a Sensitivity Tornado Diagram, or a 100-path Geometric Brownian Motion (GBM) Spaghetti Plot.
* **Dynamic Peer Comparison:** Automatically routes the target ticker to 4 relative industry competitors based on sector metadata. Compare P/E, P/B, Operating Margins, and ROE in an interactive, clickable grid that lets you swap the active dashboard target instantly.
* **Institutional Excel Export:** Click to download a fully formatted, multi-sheet `.xlsx` file containing the tuned DCF assumptions, a 5-year FCF forecast schedule, terminal value breakdown, and a Bear/Base/Bull scenario analysis matrix.
* **Live News & Sentiment:** Fetches the latest 6 headlines for the target company using a robust RSS parser, automatically scoring the sentiment (Bullish, Bearish, or Neutral) of each headline using natural language processing.

## Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/YOUR_USERNAME/financial-market-terminal.git](https://github.com/YOUR_USERNAME/financial-market-terminal.git)
   cd financial-market-terminal

## Dependencies

* `streamlit` - Interactive terminal UI and reactive components
* `yfinance` - Real-time and historical pricing, metadata, and financial statements
* `pandas` & `numpy` - Vectorized calculations, cash flow scheduling, and Monte Carlo engines
* `plotly` - Multi-panel interactive charting, subplots, and distribution plots
* `xlsxwriter` - Automated institutional Excel modeling and dynamic formatting
* `textblob` - NLP sentiment classification on live financial news

## Usage

1. Launch the app and access `http://localhost:8501` in your browser.
2. Enter any ticker symbol (e.g., `AAPL`, `NVDA`, `MSFT`) in the search bar.
3. Use the timeframe pills to review technical indicators across intraday or historical bars.
4. Expand the **Interactive DCF Valuation Assumptions** panel to adjust discount rates, operating margins, or perpetual growth in real time.
5. Inspect the Monte Carlo distributions via Bell Curve, Sensitivity Tornado, or Spaghetti GBM paths.
6. Click any competitor symbol in the **Interactive Peer Comparison** table to instantly pivot the terminal to that firm.
7. Export your adjusted model directly using **Export Live DCF Model to Excel**.

---

## 🗺️ Multi-Asset Expansion Roadmap

The architecture is currently expanding beyond equities into a unified cross-asset terminal:

### Phase 1: Commodities & Energy
* **Spot & Futures Coverage:** Track major energy (`CL=F`, `NG=F`), precious metals (`GC=F`, `SI=F`), and agricultural commodities.
* **Term Structure & Curve Analytics:** Futures forward curves, contango vs. backwardation visualization, and roll-yield metrics.
* **Macro Correlation Matrix:** Real-time correlation tracking between commodities and inflation expectations.

### Phase 2: Foreign Exchange & Global Currencies
* **G10 & Emerging Market Pairs:** Live FX pricing via `EURUSD=X`, `USDJPY=X`, `GBPUSD=X`, and currency cross matrices.
* **Macro Drivers:** Central bank policy rate differentials, purchasing power parity (PPP) indicators, and real effective exchange rate (REER) tracking.
* **FX Volatility Surface:** Implied volatility comparisons and currency risk indices.

### Phase 3: Fixed Income, Rates & Sovereign Debt
* **Yield Curve Engine:** Full US Treasury term structure (`^IRX`, `^FVX`, `^TNX`, `^TYX`) with 2Y/10Y and 3M/10Y spread monitors.
* **Curve Inversion Alerts:** Automatic detection and visual signaling for yield curve inversions and recession risk.
* **Credit & Duration Metrics:** Effective duration, convexity calculators, and corporate credit spread indices (Investment Grade vs. High Yield).

### Phase 4: Digital Assets & Cryptocurrencies
* **Tier-1 Crypto Coverage:** Real-time metrics for major pairs (`BTC-USD`, `ETH-USD`, `SOL-USD`).
* **On-Chain & Market Indicators:** Bitcoin dominance ratios, 24-hour volume profiles, and aggregate stablecoin liquidity flow.
* **Cross-Asset Beta:** Quantitative beta tracking comparing digital asset performance to tech equities and gold.
