# Financial Market Terminal v2

A high-performance, single-file financial analytics dashboard built with Streamlit, yfinance, and Plotly. Version 2 introduces professional-grade risk metrics, a fully synchronized valuation engine, advanced technical charting, and massive performance optimizations.

## 🚀 What's New in v2

### Valuation & Monte Carlo Engines
* **Synchronized DCF & Monte Carlo:** The 10,000-iteration Monte Carlo simulation is now fully vectorized using `numpy` and directly inherits the DCF slider inputs, ensuring the median simulation perfectly matches the headline intrinsic value[cite: 1].
* **Scenario Presets:** Quickly apply "Consensus Base," "Recession Shock," or "Tech Boom" scenarios to WACC, growth, and margin assumptions[cite: 1].
* **Advanced Visualizations:** The Monte Carlo suite now includes a Fan-chart view for better distribution communication and a fixed Tornado diagram for sensitivity analysis[cite: 1].
* **Live Excel Export:** Generate and download a fully formatted DCF Excel model on the fly[cite: 1].

### Risk & Quality Panel
A newly added panel offering institutional-grade screening metrics, safely handling missing data with robust `N/A` fallbacks[cite: 1]:
* **Cash & Valuation:** FCF yield and EV/FCF[cite: 1].
* **Profitability:** ROIC and the ROIC minus WACC spread[cite: 1].
* **Leverage:** Net debt / EBITDA and Interest coverage[cite: 1].
* **Earnings Quality:** Sloan accrual ratio (screens for earnings not backed by cash)[cite: 1].
* **Tail Risk:** 3-Year Historical VaR 95%, CVaR, Parametric VaR, and Max Drawdown[cite: 1].

### Technical Charting
* **Customizable Plotly Charts:** Toggle between Candles/Line and Linear/Log scales[cite: 1]. 
* **Indicators & Overlays:** Easily apply Bollinger Bands, SMA 50, SMA 200, EMA 20, VWAP, Volume, RSI, MACD, and ATR[cite: 1]. SMA 200 now utilizes warm-up history so it calculates correctly on the first visible bar[cite: 1].
* **Clean Data:** Removed weekend, holiday, and overnight gaps from the x-axis for contiguous, professional charting[cite: 1].

### UI/UX & Performance Optimization
* **Responsive KPI Cards:** Replaced default Streamlit metrics with custom HTML/CSS cards featuring a subtle gradient and auto-fitting grid layout, preventing text clipping and standardizing heights[cite: 1].
* **Intelligent Caching:** Peer data and financial metrics are now wrapped in `@st.cache_data(ttl=600)`, drastically reducing UI lag and sequential API calls during interactive widget use[cite: 1].
* **Custom Peer Analysis:** Users can now input their own comma-separated list of custom peers, which overrides the dynamic sector-based defaults[cite: 1].
* **Security:** News headlines and URLs are now safely HTML-escaped[cite: 1].

## 🛠️ Installation & Usage

### Requirements
The dashboard requires Python 3.8+ and Streamlit 1.40 or newer[cite: 1]. 

Install the required dependencies:
```bash
pip install streamlit>=1.40 yfinance plotly pandas numpy xlsxwriter textblob