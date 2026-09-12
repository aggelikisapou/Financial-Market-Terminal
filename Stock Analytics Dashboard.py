import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import io
import urllib.request
import xml.etree.ElementTree as ET
import email.utils
from datetime import datetime
from textblob import TextBlob

# ==========================================
# 1. PAGE CONFIGURATION & THEME STYLING
# ==========================================
st.set_page_config(page_title="Financial Market Terminal", layout="wide", initial_sidebar_state="collapsed")

if 'search_ticker' not in st.session_state:
    st.session_state.search_ticker = ""

st.markdown("""
    <style>
    .stApp {
        background-color: #080e18;
        color: #e0e6ed;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .css-1r6slb0, .css-1y4p8pa, .st-emotion-cache-1y4p8pa, .st-emotion-cache-1r6slb0 {
        background-color: #131f33 !important;
        border: 1px solid #1e3252 !important;
        border-radius: 8px !important;
        padding: 15px;
    }
    h1, h2, h3, h4, h5, h6 { color: #ffffff !important; }
    p, div { color: #cfd8dc; }
    .stButton>button {
        background-color: #1e88e5;
        color: white;
        border: none;
        border-radius: 4px;
        transition: all 0.3s;
    }
    .stButton>button:hover { background-color: #007acc; border-color: #007acc; color: white;}
    
/* Refined Metric Cards for Uniform Grid Alignment */
    [data-testid="stMetric"] {
        background-color: #131f33;
        border: 1px solid #1e3252;
        padding: 12px 15px;
        border-radius: 8px;
        min-height: 110px; 
        display: flex;
        flex-direction: column;
        justify-content: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        /* Prevent accidental text highlighting */
        -webkit-user-select: none; 
        -moz-user-select: none;
        -ms-user-select: none;
        user-select: none; 
    }
    [data-testid="stMetricLabel"] {
        font-size: 13px !important;
        color: #8a99a8 !important;
        margin-bottom: 2px;
    }
    [data-testid="stMetricValue"] {
        font-size: 19px !important; /* Scaled down slightly to fit 52W ranges naturally */
        font-weight: 700 !important;
        color: #ffffff !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 13px !important;
    }
    
    .peer-header { font-size: 15px; font-weight: bold; color: #cfd8dc; padding-bottom: 8px; border-bottom: 1px solid #1e3252; margin-bottom: 10px; text-align: center;}
    .peer-cell { font-size: 15px; color: #ffffff; margin-top: 8px; text-align: center; font-weight: 500;}
    
    .badge-bullish { background-color: #00e676; color: #000; padding: 3px 8px; border-radius: 12px; font-weight: bold; font-size: 12px;}
    .badge-bearish { background-color: #ff3d57; color: #fff; padding: 3px 8px; border-radius: 12px; font-weight: bold; font-size: 12px;}
    .badge-neutral { background-color: #1e88e5; color: #fff; padding: 3px 8px; border-radius: 12px; font-weight: bold; font-size: 12px;}
    </style>
""", unsafe_allow_html=True)


# ==========================================
# 2. HELPER FUNCTIONS & DATA FETCHING
# ==========================================
@st.cache_resource(ttl=300)
def fetch_ticker_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    if 'regularMarketPrice' not in info and 'currentPrice' not in info:
        return None, None
    return ticker, info

@st.cache_data(ttl=300)
def fetch_chart_data(ticker_symbol, timeframe):
    tf_map = {
        '1D': ('1d', '5m'), '1W': ('5d', '30m'), '1M': ('1mo', '1d'),
        '3M': ('3mo', '1d'), '6M': ('6mo', '1d'), '1Y': ('1y', '1d'),
        '5Y': ('5y', '1wk'), 'Max': ('max', '1mo')
    }
    period, interval = tf_map.get(timeframe, ('1y', '1d'))
    hist = yf.download(ticker_symbol, period=period, interval=interval, progress=False)
    if isinstance(hist.columns, pd.MultiIndex):
        hist.columns = hist.columns.get_level_values(0)
    return hist

def calculate_interactive_dcf(info, current_price, wacc=0.085, terminal_g=0.025, target_margin=0.15):
    eps = info.get('trailingEps')
    if eps is None or eps <= 0:
        eps = max(current_price / 20.0, 1.0)
    
    base_margin = info.get('operatingMargins', 0.15)
    if base_margin is None or base_margin <= 0:
        base_margin = 0.15
    margin_multiplier = target_margin / base_margin
    adjusted_eps = eps * margin_multiplier
    
    growth_rate = info.get('revenueGrowth', 0.05)
    if growth_rate is None or growth_rate < 0:
        growth_rate = 0.04
    
    eff_wacc = max(wacc, terminal_g + 0.005)
    
    cash_flows = [adjusted_eps * ((1 + growth_rate) ** i) for i in range(1, 6)]
    terminal_value = (cash_flows[-1] * (1 + terminal_g)) / (eff_wacc - terminal_g)
    pv_cf = sum([cf / ((1 + eff_wacc) ** i) for i, cf in enumerate(cash_flows, 1)])
    pv_tv = terminal_value / ((1 + eff_wacc) ** 5)
    
    intrinsic_val = max(pv_cf + pv_tv, 0.01)
    return intrinsic_val, cash_flows, pv_cf, pv_tv, terminal_value

def generate_bofa_style_dcf_excel(ticker, current_price, intrinsic_val, wacc, term_g, margin, cfs, terminal_value, info):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'bg_color': '#1f497d', 'font_color': 'white'})
        header_fmt = workbook.add_format({'bold': True, 'bottom': 1, 'bg_color': '#dce6f1'})
        currency_fmt = workbook.add_format({'num_format': '$#,##0.00'})
        pct_fmt = workbook.add_format({'num_format': '0.0%'})
        
        sheet = workbook.add_worksheet('DCF Model')
        sheet.set_column('A:A', 35)
        sheet.set_column('B:F', 15)
        
        sheet.write('A1', f'{ticker} - Discounted Cash Flow Analysis', title_fmt)
        
        sheet.write('A3', 'Key Assumptions (Base Case)', header_fmt)
        sheet.write('A4', 'Target Operating Margin')
        sheet.write('B4', margin, pct_fmt)
        sheet.write('A5', 'Discount Rate (WACC)')
        sheet.write('B5', wacc, pct_fmt)
        sheet.write('A6', 'Perpetual Growth Rate (g)')
        sheet.write('B6', term_g, pct_fmt)
        
        sheet.write('A8', 'Forecasted Cash Flows (Per Share)', header_fmt)
        years = ['Year 1', 'Year 2', 'Year 3', 'Year 4', 'Year 5']
        for col_num, year in enumerate(years, 1):
            sheet.write(8, col_num, year, header_fmt)
            
        sheet.write('A10', 'Adjusted Free Cash Flow')
        sheet.write('A11', 'Discount Factor')
        sheet.write('A12', 'Present Value of FCF')
        
        eff_wacc = max(wacc, term_g + 0.005)
        pv_cfs_list = []
        for i, cf in enumerate(cfs):
            df = 1 / ((1 + eff_wacc) ** (i + 1))
            pv = cf * df
            pv_cfs_list.append(pv)
            sheet.write(9, i + 1, cf, currency_fmt)
            sheet.write(10, i + 1, df)
            sheet.write(11, i + 1, pv, currency_fmt)
            
        sheet.write('A14', 'Valuation Summary', header_fmt)
        sheet.write('A15', 'Sum of PV of Cash Flows')
        sheet.write('B15', sum(pv_cfs_list), currency_fmt)
        
        sheet.write('A16', 'Terminal Value (Gordon Growth)')
        sheet.write('B16', terminal_value, currency_fmt)
        
        pv_tv = terminal_value / ((1 + eff_wacc) ** 5)
        sheet.write('A17', 'Present Value of Terminal Value')
        sheet.write('B17', pv_tv, currency_fmt)
        
        sheet.write('A19', 'Implied Intrinsic Value', title_fmt)
        sheet.write('B19', intrinsic_val, currency_fmt)
        
        sheet.write('A20', 'Current Share Price')
        sheet.write('B20', current_price, currency_fmt)
        
        upside = (intrinsic_val / current_price) - 1 if current_price else 0
        sheet.write('A21', 'Implied Upside / (Downside)')
        sheet.write('B21', upside, pct_fmt)
        
        sheet.write('A24', 'Scenario Analysis Matrix', title_fmt)
        sheet.write('A25', 'Metric', header_fmt)
        sheet.write('B25', 'Bear Case', header_fmt)
        sheet.write('C25', 'Base Case', header_fmt)
        sheet.write('D25', 'Bull Case', header_fmt)
        
        bear_val, _, _, _, _ = calculate_interactive_dcf(info, current_price, wacc=wacc+0.015, terminal_g=term_g-0.005, target_margin=margin-0.03)
        bull_val, _, _, _, _ = calculate_interactive_dcf(info, current_price, wacc=wacc-0.015, terminal_g=term_g+0.005, target_margin=margin+0.03)
        
        sheet.write('A26', 'WACC Assumption')
        sheet.write('B26', wacc + 0.015, pct_fmt)
        sheet.write('C26', wacc, pct_fmt)
        sheet.write('D26', wacc - 0.015, pct_fmt)
        
        sheet.write('A27', 'Operating Margin Assumption')
        sheet.write('B27', margin - 0.03, pct_fmt)
        sheet.write('C27', margin, pct_fmt)
        sheet.write('D27', margin + 0.03, pct_fmt)
        
        sheet.write('A28', 'Implied Fair Value')
        sheet.write('B28', bear_val, currency_fmt)
        sheet.write('C28', intrinsic_val, currency_fmt)
        sheet.write('D28', bull_val, currency_fmt)
        
    return output.getvalue()

def run_dcf_monte_carlo(info, base_price, base_wacc, base_margin, iterations=10000):
    np.random.seed(42)
    wacc_dist = np.random.normal(base_wacc, 0.01, iterations)
    growth_dist = np.random.normal(info.get('revenueGrowth', 0.05) or 0.05, 0.02, iterations)
    margin_dist = np.random.normal(base_margin, 0.02, iterations)
    eps = info.get('trailingEps', base_price/15)
    if eps is None or eps <= 0: eps = base_price / 15
    simulated_values = []
    
    for w, g, m in zip(wacc_dist, growth_dist, margin_dist):
        g, w = max(0.0, g), max(0.04, w)
        cfs = [eps * ((1 + g) ** i) * (1 + max(0.01, m)) for i in range(1, 6)]
        tv = (cfs[-1] * 1.02) / (w - 0.02) if w > 0.02 else 0
        pv = sum([cf / ((1 + w) ** i) for i, cf in enumerate(cfs, 1)]) + (tv / ((1 + w) ** 5))
        simulated_values.append(pv)
    return np.array(simulated_values), wacc_dist, growth_dist, margin_dist

@st.cache_data(ttl=300)
def run_price_paths_gbm(hist_data, current_price, days=252, simulations=100):
    returns = hist_data['Close'].pct_change().dropna()
    mu = returns.mean()
    sigma = returns.std()
    paths = np.zeros((days, simulations))
    paths[0] = current_price
    for t in range(1, days):
        rand_shocks = np.random.standard_normal(simulations)
        paths[t] = paths[t-1] * np.exp((mu - 0.5 * sigma**2) + sigma * rand_shocks)
    return paths

@st.cache_data(ttl=600)
def fetch_company_news(ticker_symbol):
    try:
        url = f"https://news.google.com/rss/search?q={ticker_symbol}+stock+news&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        items = root.findall('.//item')
        parsed = []
        for item in items[:6]:
            pub_date_str = item.find('pubDate').text
            time_tuple = email.utils.parsedate_tz(pub_date_str)
            ts = email.utils.mktime_tz(time_tuple) if time_tuple else datetime.now().timestamp()
            
            full_title = item.find('title').text
            if " - " in full_title:
                title, publisher = full_title.rsplit(" - ", 1)
            else:
                title, publisher = full_title, "Financial News"
                
            parsed.append({'title': title, 'link': item.find('link').text, 'publisher': publisher, 'published': ts})
        if parsed: return parsed
    except: pass
    return []

def get_sentiment(text):
    score = TextBlob(text).sentiment.polarity
    if score > 0.1: return 'Bullish', 'badge-bullish'
    elif score < -0.1: return 'Bearish', 'badge-bearish'
    return 'Neutral', 'badge-neutral'

def get_dynamic_peers(ticker_symbol, info):
    sector = info.get('sector', 'Technology')
    sector_map = {
        'Technology': ['MSFT', 'AAPL', 'GOOGL', 'META', 'NVDA', 'ORCL'],
        'Consumer Cyclical': ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX'],
        'Financial Services': ['JPM', 'V', 'MA', 'BAC', 'WFC', 'GS'],
        'Healthcare': ['UNH', 'JNJ', 'LLY', 'ABBV', 'PFE', 'MRK'],
        'Communication Services': ['GOOGL', 'META', 'NFLX', 'DIS', 'CMCSA', 'TMUS'],
        'Industrials': ['CAT', 'UNP', 'BA', 'HON', 'GE', 'UPS'],
        'Consumer Defensive': ['WMT', 'PG', 'KO', 'PEP', 'COST', 'PM'],
        'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY']
    }
    candidates = sector_map.get(sector, sector_map['Technology'])
    return [p for p in candidates if p != ticker_symbol][:4]


# ==========================================
# 3. HEADER & SEARCH
# ==========================================
st.markdown("<h2>⚡ Financial Market Terminal</h2>", unsafe_allow_html=True)
col_search, col_btn = st.columns([4, 1])

with col_search:
    user_input = st.text_input("", placeholder="Enter Ticker (e.g., AAPL, MSFT, TSLA)...", value=st.session_state.search_ticker)

if user_input.upper() != st.session_state.search_ticker:
    st.session_state.search_ticker = user_input.upper()
    st.rerun()

ticker_input = st.session_state.search_ticker

if not ticker_input:
    st.info("Please enter a stock ticker in the search bar above to generate the dashboard.")
    st.stop()

ticker, info = fetch_ticker_data(ticker_input)
if not ticker or info is None:
    st.error(f"Failed to fetch data for '{ticker_input}'. Please check the ticker symbol.")
    st.stop()

current_price = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
prev_close = info.get('previousClose', current_price)

low_52 = info.get('fiftyTwoWeekLow')
high_52 = info.get('fiftyTwoWeekHigh')
range_52 = f"${low_52:.1f} - {high_52:.1f}" if low_52 and high_52 else "N/A"

div_yield = info.get('dividendYield')
if div_yield is not None and div_yield > 0:
    div_yield_val = div_yield * 100 if div_yield < 1.0 else div_yield
    div_yield_str = f"{div_yield_val:.2f}%"
else:
    div_yield_str = "0.00% (None)"

beta = info.get('beta')
beta_str = f"{beta:.2f}" if beta is not None else "N/A"

hist_1y = fetch_chart_data(ticker_input, '1Y')
if not hist_1y.empty and len(hist_1y) > 20:
    ann_vol = hist_1y['Close'].pct_change().dropna().std() * np.sqrt(252) * 100
    vol_str = f"{ann_vol:.1f}%"
else:
    vol_str = "N/A"


# ==========================================
# 4. DASHBOARD LAYOUT
# ==========================================
top_col1, top_col2 = st.columns([6, 4])

with top_col1:
    st.markdown(f"<h3>{info.get('shortName', ticker_input)} ({ticker_input})</h3>", unsafe_allow_html=True)
    
    tf_selected = st.radio("Timeframe", ['1D', '1W', '1M', '3M', '6M', '1Y', '5Y', 'Max'], horizontal=True, index=5)
    hist = fetch_chart_data(ticker_input, tf_selected)
    
    if not hist.empty and len(hist) > 0:
        if tf_selected == '1D' and prev_close:
            period_change = current_price - prev_close
            period_pct = (period_change / prev_close) * 100
        else:
            base_price = float(hist['Close'].iloc[0])
            period_change = current_price - base_price
            period_pct = (period_change / base_price) * 100
    else:
        period_change = current_price - prev_close
        period_pct = (period_change / prev_close) * 100

    default_margin = max(1.0, min(60.0, float((info.get('operatingMargins', 0.15) or 0.15) * 100)))
    with st.expander("🎛️ Interactive DCF Valuation Assumptions", expanded=False):
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            wacc_val = st.slider("WACC / Discount Rate", min_value=4.0, max_value=16.0, value=8.5, step=0.1, format="%.1f%%") / 100.0
        with sc2:
            term_g_val = st.slider("Terminal Growth Rate (g)", min_value=0.5, max_value=5.0, value=2.5, step=0.1, format="%.1f%%") / 100.0
        with sc3:
            op_margin_val = st.slider("Operating Margin", min_value=1.0, max_value=60.0, value=default_margin, step=0.5, format="%.1f%%") / 100.0
            
        intrinsic_val, projected_cfs, pv_cfs, pv_tv, terminal_value = calculate_interactive_dcf(
            info, current_price, wacc=wacc_val, terminal_g=term_g_val, target_margin=op_margin_val
        )
        
        excel_data = generate_bofa_style_dcf_excel(ticker_input, current_price, intrinsic_val, wacc_val, term_g_val, op_margin_val, projected_cfs, terminal_value, info)
        st.download_button(
            label="📥 Export Live DCF Model to Excel",
            data=excel_data,
            file_name=f"{ticker_input}_DCF_Model.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    dcf_diff = intrinsic_val - current_price
    dcf_upside = (dcf_diff / current_price) * 100 if current_price else 0

    r1_c1, r1_c2, r1_c3, r1_c4 = st.columns(4)
    r1_c1.metric("Current Price", f"${current_price:.2f}", f"{period_change:+.2f} ({period_pct:+.2f}%)")
    r1_c2.metric("Intrinsic Value (DCF)", f"${intrinsic_val:.2f}", f"{dcf_upside:+.1f}% vs Price")
    r1_c3.metric("52-Week Range", range_52)
    r1_c4.metric("Market Cap", f"${info.get('marketCap', 0)/1e9:.2f}B" if info.get('marketCap') else "N/A")

    r2_c1, r2_c2, r2_c3, r2_c4 = st.columns(4)
    r2_c1.metric("Trailing EPS", f"${info.get('trailingEps', 'N/A')}")
    r2_c2.metric("Dividend Yield", div_yield_str)
    r2_c3.metric("LT Growth (g)", f"{term_g_val*100:.1f}% (Tuned)")
    r2_c4.metric("Volatility (Ann.)", vol_str, f"Beta: {beta_str}", delta_color="off")

    if not hist.empty:
        if len(hist) > 20:
            hist['SMA20'] = hist['Close'].rolling(window=20).mean()
            hist['STD20'] = hist['Close'].rolling(window=20).std()
            hist['BB_Up'] = hist['SMA20'] + (hist['STD20'] * 2)
            hist['BB_Low'] = hist['SMA20'] - (hist['STD20'] * 2)
            
        if len(hist) > 14:
            delta = hist['Close'].diff()
            gain = delta.where(delta > 0, 0.0)
            loss = -delta.where(delta < 0, 0.0)
            avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
            rs = avg_gain / avg_loss
            hist['RSI'] = 100 - (100 / (1 + rs))

        fig_chart = go.Figure()
        
        fig_chart.add_trace(go.Candlestick(
            x=hist.index, open=hist['Open'], high=hist['High'],
            low=hist['Low'], close=hist['Close'], name='Price',
            increasing_line_color='#00e676', decreasing_line_color='#ff3d57'
        ))
        
        if len(hist) > 20:
            fig_chart.add_trace(go.Scatter(x=hist.index, y=hist['BB_Up'], line=dict(color='rgba(173, 216, 230, 0.4)', width=1), name='BB Upper'))
            fig_chart.add_trace(go.Scatter(x=hist.index, y=hist['BB_Low'], line=dict(color='rgba(173, 216, 230, 0.4)', width=1), fill='tonexty', fillcolor='rgba(173, 216, 230, 0.1)', name='BB Lower'))
            
        if tf_selected not in ['1D', '1W'] and len(hist) > 50:
            hist['SMA50'] = hist['Close'].rolling(window=50).mean()
            fig_chart.add_trace(go.Scatter(x=hist.index, y=hist['SMA50'], line=dict(color='#1e88e5', width=1.5), name='50 SMA'))
        if tf_selected not in ['1D', '1W'] and len(hist) > 200:
            hist['SMA200'] = hist['Close'].rolling(window=200).mean()
            fig_chart.add_trace(go.Scatter(x=hist.index, y=hist['SMA200'], line=dict(color='#cfd8dc', width=1.5), name='200 SMA'))

        colors = ['#00e676' if row['Close'] >= row['Open'] else '#ff3d57' for _, row in hist.iterrows()]
        fig_chart.add_trace(go.Bar(x=hist.index, y=hist['Volume'], marker_color=colors, name='Volume', yaxis='y2', opacity=0.4))
        
        if len(hist) > 14:
            fig_chart.add_trace(go.Scatter(x=hist.index, y=hist['RSI'], line=dict(color='#ff9800', width=1.5), name='RSI', yaxis='y3'))
            fig_chart.add_hline(y=70, line_dash="dash", line_color="#ff3d57", line_width=1, yref='y3', opacity=0.7)
            fig_chart.add_hline(y=30, line_dash="dash", line_color="#00e676", line_width=1, yref='y3', opacity=0.7)

        fig_chart.update_layout(
            template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=20, b=0),
            yaxis=dict(title='Price', domain=[0.45, 1]),
            yaxis2=dict(title='Volume', domain=[0.25, 0.43], showgrid=False),
            yaxis3=dict(title='RSI (14)', domain=[0.0, 0.23], showgrid=False, range=[0, 100]),
            xaxis=dict(rangeslider=dict(visible=False)), 
            height=600, showlegend=False
        )
        st.plotly_chart(fig_chart, use_container_width=True)

with top_col2:
    st.markdown("<h4>Interactive Peer Comparison</h4>", unsafe_allow_html=True)
    st.markdown("<p style='color:#8a99a8; font-size: 13px; margin-bottom:10px;'>Click any competitor's ticker button to reload the terminal.</p>", unsafe_allow_html=True)
    
    peers = get_dynamic_peers(ticker_input, info)
    peer_data = [{
        'Ticker': ticker_input, 'P/E': round(info.get('trailingPE', 0) or 0, 1),
        'Fwd P/E': round(info.get('forwardPE', 0) or 0, 1), 'P/B': round(info.get('priceToBook', 0) or 0, 2),
        'Op Margin': f"{info.get('operatingMargins', 0)*100:.1f}%", 'ROE': f"{info.get('returnOnEquity', 0)*100:.1f}%"
    }]
    
    for p in peers:
        try:
            p_info = yf.Ticker(p).info
            peer_data.append({
                'Ticker': p, 'P/E': round(p_info.get('trailingPE', 0) or 0, 1),
                'Fwd P/E': round(p_info.get('forwardPE', 0) or 0, 1), 'P/B': round(p_info.get('priceToBook', 0) or 0, 2),
                'Op Margin': f"{p_info.get('operatingMargins', 0)*100:.1f}%" if p_info.get('operatingMargins') else "N/A",
                'ROE': f"{p_info.get('returnOnEquity', 0)*100:.1f}%" if p_info.get('returnOnEquity') else "N/A"
            })
        except: pass
    
    hc1, hc2, hc3, hc4, hc5, hc6 = st.columns([1.5, 1, 1, 1, 1, 1])
    hc1.markdown("<div class='peer-header'>Ticker</div>", unsafe_allow_html=True)
    hc2.markdown("<div class='peer-header'>P/E</div>", unsafe_allow_html=True)
    hc3.markdown("<div class='peer-header'>Fwd P/E</div>", unsafe_allow_html=True)
    hc4.markdown("<div class='peer-header'>P/B</div>", unsafe_allow_html=True)
    hc5.markdown("<div class='peer-header'>Margin</div>", unsafe_allow_html=True)
    hc6.markdown("<div class='peer-header'>ROE</div>", unsafe_allow_html=True)
    
    for row in peer_data:
        rc1, rc2, rc3, rc4, rc5, rc6 = st.columns([1.5, 1, 1, 1, 1, 1])
        with rc1:
            if st.button(row['Ticker'], key=f"peer_{row['Ticker']}", use_container_width=True):
                st.session_state.search_ticker = row['Ticker']
                st.rerun()
        rc2.markdown(f"<div class='peer-cell'>{row['P/E']}</div>", unsafe_allow_html=True)
        rc3.markdown(f"<div class='peer-cell'>{row['Fwd P/E']}</div>", unsafe_allow_html=True)
        rc4.markdown(f"<div class='peer-cell'>{row['P/B']}</div>", unsafe_allow_html=True)
        rc5.markdown(f"<div class='peer-cell'>{row['Op Margin']}</div>", unsafe_allow_html=True)
        rc6.markdown(f"<div class='peer-cell'>{row['ROE']}</div>", unsafe_allow_html=True)
    
    target_pe = peer_data[0]['P/E']
    median_pe = pd.Series([r['P/E'] for r in peer_data[1:]]).replace(0, np.nan).median()
    if pd.notna(median_pe) and target_pe > 0:
        if target_pe < (median_pe * 0.9): callout = "<span style='color:#00e676;'>Undervalued (Cheap)</span>"
        elif target_pe > (median_pe * 1.1): callout = "<span style='color:#ff3d57;'>Overvalued (Expensive)</span>"
        else: callout = "<span style='color:#1e88e5;'>Fairly Valued</span>"
        st.markdown(f"<br>**Relative Valuation Signal:** {callout} vs Sector Median P/E", unsafe_allow_html=True)
    
    st.divider()

    st.markdown("<h4>Monte Carlo Simulation (10k Iters)</h4>", unsafe_allow_html=True)
    sim_values, wacc_dist, g_dist, m_dist = run_dcf_monte_carlo(info, current_price, base_wacc=wacc_val, base_margin=op_margin_val, iterations=10000)
    p10, p50, p90 = np.percentile(sim_values, 10), np.percentile(sim_values, 50), np.percentile(sim_values, 90)

    sim_view = st.pills("Simulation View", ["Bell Curve", "Tornado Diagram", "Spaghetti Plot"], default="Spaghetti Plot")
    
    if sim_view == "Bell Curve":
        fig_mc = px.histogram(sim_values, nbins=100, color_discrete_sequence=['#1e88e5'])
        fig_mc.add_vline(x=p10, line_dash="dash", line_color="#ff3d57", annotation_text="Bear")
        fig_mc.add_vline(x=p50, line_dash="solid", line_color="#ffffff", annotation_text="Base")
        fig_mc.add_vline(x=p90, line_dash="dash", line_color="#00e676", annotation_text="Bull")
        fig_mc.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False, xaxis_title="Simulated Intrinsic Value ($)", yaxis_title="Frequency", height=230, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_mc, use_container_width=True)
        
    elif sim_view == "Tornado Diagram":
        sens_df = pd.DataFrame({'Variable': ['WACC', 'Revenue Growth', 'Operating Margin'], 'Impact Coefficient': [np.corrcoef(wacc_dist, sim_values)[0,1] * -1, np.corrcoef(g_dist, sim_values)[0,1], np.corrcoef(m_dist, sim_values)[0,1]]}).sort_values(by='Impact Coefficient', ascending=True)
        fig_tornado = px.bar(sens_df, x='Impact Coefficient', y='Variable', orientation='h', color='Impact Coefficient', color_continuous_scale=['#ff3d57', '#131f33', '#00e676'])
        fig_tornado.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=230, margin=dict(l=0, r=0, t=10, b=0), coloraxis_showscale=False)
        st.plotly_chart(fig_tornado, use_container_width=True)
        
    else:
        if not hist.empty:
            gbm_paths = run_price_paths_gbm(hist, current_price, days=252, simulations=100)
            fig_spag = go.Figure()
            palette = px.colors.qualitative.Light24 + px.colors.qualitative.Alphabet
            
            for i in range(gbm_paths.shape[1]):
                line_color = palette[i % len(palette)]
                fig_spag.add_trace(go.Scatter(y=gbm_paths[:, i], mode='lines', line=dict(width=1.5, color=line_color), opacity=0.4, showlegend=False))
                
            fig_spag.add_trace(go.Scatter(y=np.median(gbm_paths, axis=1), mode='lines', line=dict(width=3.5, color='#ffffff'), name='Median Path'))
            fig_spag.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis_title="Trading Days in Future", yaxis_title="Simulated Price ($)", height=230, margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
            st.plotly_chart(fig_spag, use_container_width=True)

    st.markdown(f"""
    <table style="width:100%; text-align:center; border:1px solid #1e3252;">
        <tr style="background-color:#1e3252;"><th>Bearish (10th)</th><th>Median (50th)</th><th>Bullish (90th)</th></tr>
        <tr><td>${p10:.2f}</td><td style="color:#1e88e5; font-weight:bold;">${p50:.2f}</td><td>${p90:.2f}</td></tr>
    </table>
    """, unsafe_allow_html=True)


# ==========================================
# 5. LOWER SECTION: NEWS
# ==========================================
st.divider()
st.markdown("<h4>Live Company News & Analyst Sentiment</h4>", unsafe_allow_html=True)

news_items = fetch_company_news(ticker_input)

if not news_items:
    st.warning("News feed currently unavailable for this ticker.")
else:
    cols = st.columns(3)
    for i, item in enumerate(news_items):
        with cols[i % 3]:
            hours_ago = int((datetime.now().timestamp() - item['published']) / 3600)
            if hours_ago < 1: time_str = "Just now"
            elif hours_ago < 24: time_str = f"{hours_ago}h ago"
            else: time_str = f"{hours_ago // 24}d ago"
            
            headline = item['title']
            link = item['link']
            publisher = item['publisher']
            
            sentiment, badge_class = get_sentiment(headline)
            
            st.markdown(f"""
            <div style="background-color:#131f33; padding:15px; border-radius:8px; border:1px solid #1e3252; margin-bottom:15px; height: 160px; overflow: hidden;">
                <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
                    <span style="color:#8a99a8; font-size:12px; font-weight:bold;">📰 {publisher[:15]} • {time_str}</span>
                    <span class="{badge_class}">{sentiment}</span>
                </div>
                <a href="{link}" target="_blank" style="color:#ffffff; text-decoration:none; font-weight:bold; font-size:14px; line-height: 1.4;">
                    {headline}
                </a>
            </div>
            """, unsafe_allow_html=True)