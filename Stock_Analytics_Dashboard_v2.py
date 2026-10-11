"""
Financial Market Terminal - v2 (single file, no extra modules needed).

Run:   streamlit run Stock_Analytics_Dashboard_v2.py
Needs: streamlit>=1.40 yfinance plotly pandas numpy xlsxwriter textblob

What's new vs v1
  * Risk & Quality panel (FCF yield, EV/FCF, ROIC vs WACC, Net debt/EBITDA, interest cover,
    accrual ratio, 1-day VaR/CVaR, max drawdown)
  * Technical chart with toggles: candles/line, linear/log, Bollinger/SMA/EMA/VWAP, Volume/RSI/MACD/ATR
  * Scenario presets, custom peer box, fan-chart view
  * Bug fixes: GBM volatility scale, Monte Carlo now consistent with the DCF sliders,
    tornado sign, dividend yield, None-safe peers, cached peer fetch, escaped news HTML,
    warm-up history for SMA200, no more hashed CSS selectors
"""
import email.utils
import html
import io
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from statistics import NormalDist

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots
from textblob import TextBlob

# ==========================================
# 1. PAGE CONFIGURATION & THEME STYLING
# ==========================================
st.set_page_config(page_title="Financial Market Terminal", layout="wide", initial_sidebar_state="collapsed")

GREEN, RED, AMBER, BLUE = "#00e676", "#ff3d57", "#ff9800", "#1e88e5"

if "search_ticker" not in st.session_state:
    st.session_state.search_ticker = ""

st.markdown("""
<style>
.stApp { background-color: #080e18; color: #e0e6ed;
         font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
h1, h2, h3, h4, h5, h6 { color: #ffffff !important; }
p, div { color: #cfd8dc; }
.stButton>button { background-color: #1e88e5; color: white; border: none; border-radius: 4px; transition: all 0.3s; }
.stButton>button:hover { background-color: #007acc; border-color: #007acc; color: white; }

/* Cards for the right-hand panels (containers created with key="peer_card" / "mc_card") */
.st-key-peer_card, .st-key-mc_card { background-color: #131f33; border-color: #1e3252 !important; border-radius: 8px; }

/* Auto-fitting KPI grid: 4 across on wide screens, wraps cleanly on narrow ones. */
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(168px, 1fr)); gap: 10px; margin: 4px 0 14px; }
.kpi { min-width: 0; min-height: 98px; padding: 11px 14px; border: 1px solid #1e3252; border-radius: 8px;
       background: linear-gradient(165deg, #172742 0%, #131f33 60%);
       display: flex; flex-direction: column; justify-content: center; gap: 3px; transition: border-color .15s ease; }
.kpi:hover { border-color: #1e88e5; }
.kpi-label { font-size: 12px; color: #8a99a8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi-value { font-size: clamp(16px, 1.35vw, 20px); font-weight: 700; color: #fff; font-variant-numeric: tabular-nums;
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi-sub { font-size: 12px; line-height: 16px; min-height: 16px; color: #8a99a8;
           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi-sub.pos { color: #00e676; } .kpi-sub.neg { color: #ff3d57; } .kpi-sub.warn { color: #ff9800; }

.peer-header { font-size: 15px; font-weight: bold; color: #cfd8dc; padding-bottom: 8px; border-bottom: 1px solid #1e3252; margin-bottom: 10px; text-align: center; }
.peer-cell { font-size: 15px; color: #ffffff; margin-top: 8px; text-align: center; font-weight: 500; }

.badge-bullish { background-color: #00e676; color: #000; padding: 3px 8px; border-radius: 12px; font-weight: bold; font-size: 12px; }
.badge-bearish { background-color: #ff3d57; color: #fff; padding: 3px 8px; border-radius: 12px; font-weight: bold; font-size: 12px; }
.badge-neutral { background-color: #1e88e5; color: #fff; padding: 3px 8px; border-radius: 12px; font-weight: bold; font-size: 12px; }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. SMALL UI HELPERS
# ==========================================
def esc(text) -> str:
    """HTML-escape, and swap $ for an entity so markdown never pairs dollar signs into LaTeX."""
    return html.escape(str(text)).replace("$", "&#36;")


def kpi_card(label, value, sub="", tone="", tip="") -> str:
    return (f'<div class="kpi" title="{esc(tip)}"><div class="kpi-label">{esc(label)}</div>'
            f'<div class="kpi-value">{esc(value)}</div>'
            f'<div class="kpi-sub {tone}">{esc(sub) if sub else "&nbsp;"}</div></div>')


def render_kpi_grid(cards):
    # No newlines inside the HTML: markdown would end the HTML block at a blank line.
    st.markdown(f'<div class="kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def tone(v, good, bad, higher_is_better=True) -> str:
    if v is None:
        return ""
    if higher_is_better:
        return "pos" if v >= good else "neg" if v <= bad else "warn"
    return "pos" if v <= good else "neg" if v >= bad else "warn"


def num(x):
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def pct_str(v, d=1, signed=False):
    return "N/A" if v is None else f"{v * 100:{'+' if signed else ''}.{d}f}%"


def mult_str(v, d=1):
    return "N/A" if v is None else f"{v:.{d}f}x"


def big_str(v, cur):
    return "" if v is None else f"{v / 1e9:,.1f}B {cur}"


# ==========================================
# 3. DATA FETCHING
# ==========================================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_info(symbol: str):
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        return None
    if info.get("currentPrice") is None and info.get("regularMarketPrice") is None:
        return None
    return info


@st.cache_data(ttl=900, show_spinner=False)
def fetch_daily_closes(symbol: str, years: int = 3) -> pd.Series:
    df = yf.download(symbol, period=f"{years}y", interval="1d", auto_adjust=True, progress=False)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df["Close"].dropna()


@st.cache_data(ttl=600, show_spinner=False)
def fetch_peer_metrics(symbols: tuple) -> list:
    rows = []
    for s in symbols:
        try:
            i = yf.Ticker(s).info or {}
        except Exception:
            continue
        rows.append({"Ticker": s, "pe": num(i.get("trailingPE")), "fpe": num(i.get("forwardPE")),
                     "pb": num(i.get("priceToBook")), "om": num(i.get("operatingMargins")),
                     "roe": num(i.get("returnOnEquity"))})
    return rows


def get_dynamic_peers(ticker_symbol, info):
    sector = info.get("sector", "Technology")
    sector_map = {
        "Technology": ["MSFT", "AAPL", "GOOGL", "META", "NVDA", "ORCL"],
        "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX"],
        "Financial Services": ["JPM", "V", "MA", "BAC", "WFC", "GS"],
        "Healthcare": ["UNH", "JNJ", "LLY", "ABBV", "PFE", "MRK"],
        "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "CMCSA", "TMUS"],
        "Industrials": ["CAT", "UNP", "BA", "HON", "GE", "UPS"],
        "Consumer Defensive": ["WMT", "PG", "KO", "PEP", "COST", "PM"],
        "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "OXY"],
    }
    candidates = sector_map.get(sector, sector_map["Technology"])
    return [p for p in candidates if p != ticker_symbol][:4]


@st.cache_data(ttl=600, show_spinner=False)
def fetch_company_news(ticker_symbol):
    try:
        q = urllib.parse.quote_plus(f"{ticker_symbol} stock news")
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        parsed = []
        for item in root.findall(".//item")[:6]:
            title_el, link_el, date_el = item.find("title"), item.find("link"), item.find("pubDate")
            if title_el is None or link_el is None or not title_el.text:
                continue
            ts = datetime.now().timestamp()
            if date_el is not None and date_el.text:
                tt = email.utils.parsedate_tz(date_el.text)
                if tt:
                    ts = email.utils.mktime_tz(tt)
            full_title = title_el.text
            if " - " in full_title:
                title, publisher = full_title.rsplit(" - ", 1)
            else:
                title, publisher = full_title, "Financial News"
            parsed.append({"title": title, "link": link_el.text or "#", "publisher": publisher, "published": ts})
        return parsed
    except Exception:
        return []


def get_sentiment(text):
    score = TextBlob(text).sentiment.polarity
    if score > 0.1:
        return "Bullish", "badge-bullish"
    if score < -0.1:
        return "Bearish", "badge-bearish"
    return "Neutral", "badge-neutral"


# ==========================================
# 4. VALUATION ENGINES
# ==========================================
def dcf_inputs(info, price):
    """One source of truth for the DCF and the Monte Carlo so their medians agree."""
    eps = info.get("trailingEps")
    if eps is None or eps <= 0:
        eps = max(price / 20.0, 1.0)
    base_margin = info.get("operatingMargins")
    if base_margin is None or base_margin <= 0:
        base_margin = 0.15
    growth = info.get("revenueGrowth", 0.05)
    if growth is None or growth < 0:
        growth = 0.04
    return float(eps), float(base_margin), float(growth)


def calculate_interactive_dcf(info, current_price, wacc=0.085, terminal_g=0.025, target_margin=0.15):
    eps, base_margin, growth = dcf_inputs(info, current_price)
    adjusted_eps = eps * (target_margin / base_margin)
    eff_wacc = max(wacc, terminal_g + 0.005)

    cash_flows = [adjusted_eps * ((1 + growth) ** i) for i in range(1, 6)]
    terminal_value = (cash_flows[-1] * (1 + terminal_g)) / (eff_wacc - terminal_g)
    pv_cf = sum(cf / ((1 + eff_wacc) ** i) for i, cf in enumerate(cash_flows, 1))
    pv_tv = terminal_value / ((1 + eff_wacc) ** 5)
    intrinsic_val = max(pv_cf + pv_tv, 0.01)
    return intrinsic_val, cash_flows, pv_cf, pv_tv, terminal_value


@st.cache_data(ttl=300, show_spinner=False)
def generate_dcf_excel(ticker, current_price, intrinsic_val, wacc, term_g, margin, cfs, terminal_value, _info):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        workbook = writer.book
        title_fmt = workbook.add_format({"bold": True, "font_size": 14, "bg_color": "#1f497d", "font_color": "white"})
        header_fmt = workbook.add_format({"bold": True, "bottom": 1, "bg_color": "#dce6f1"})
        currency_fmt = workbook.add_format({"num_format": "$#,##0.00"})
        pct_fmt = workbook.add_format({"num_format": "0.0%"})

        sheet = workbook.add_worksheet("DCF Model")
        sheet.set_column("A:A", 35)
        sheet.set_column("B:F", 15)
        sheet.write("A1", f"{ticker} - Discounted Cash Flow Analysis", title_fmt)

        sheet.write("A3", "Key Assumptions (Base Case)", header_fmt)
        sheet.write("A4", "Target Operating Margin"); sheet.write("B4", margin, pct_fmt)
        sheet.write("A5", "Discount Rate (WACC)"); sheet.write("B5", wacc, pct_fmt)
        sheet.write("A6", "Perpetual Growth Rate (g)"); sheet.write("B6", term_g, pct_fmt)

        sheet.write("A8", "Forecasted Cash Flows (Per Share)", header_fmt)
        for col_num, year in enumerate(["Year 1", "Year 2", "Year 3", "Year 4", "Year 5"], 1):
            sheet.write(8, col_num, year, header_fmt)
        sheet.write("A10", "Adjusted Earnings per Share (FCF proxy)")
        sheet.write("A11", "Discount Factor")
        sheet.write("A12", "Present Value")

        eff_wacc = max(wacc, term_g + 0.005)
        pv_list = []
        for i, cf in enumerate(cfs):
            df_ = 1 / ((1 + eff_wacc) ** (i + 1))
            pv_list.append(cf * df_)
            sheet.write(9, i + 1, cf, currency_fmt)
            sheet.write(10, i + 1, df_)
            sheet.write(11, i + 1, cf * df_, currency_fmt)

        sheet.write("A14", "Valuation Summary", header_fmt)
        sheet.write("A15", "Sum of PV of Cash Flows"); sheet.write("B15", sum(pv_list), currency_fmt)
        sheet.write("A16", "Terminal Value (Gordon Growth)"); sheet.write("B16", terminal_value, currency_fmt)
        sheet.write("A17", "Present Value of Terminal Value")
        sheet.write("B17", terminal_value / ((1 + eff_wacc) ** 5), currency_fmt)
        sheet.write("A19", "Implied Intrinsic Value", title_fmt); sheet.write("B19", intrinsic_val, currency_fmt)
        sheet.write("A20", "Current Share Price"); sheet.write("B20", current_price, currency_fmt)
        sheet.write("A21", "Implied Upside / (Downside)")
        sheet.write("B21", (intrinsic_val / current_price) - 1 if current_price else 0, pct_fmt)

        sheet.write("A24", "Scenario Analysis Matrix", title_fmt)
        for c, h in zip("ABCD", ["Metric", "Bear Case", "Base Case", "Bull Case"]):
            sheet.write(f"{c}25", h, header_fmt)
        bear_val = calculate_interactive_dcf(_info, current_price, wacc + 0.015, term_g - 0.005, margin - 0.03)[0]
        bull_val = calculate_interactive_dcf(_info, current_price, wacc - 0.015, term_g + 0.005, margin + 0.03)[0]
        sheet.write("A26", "WACC Assumption")
        sheet.write("B26", wacc + 0.015, pct_fmt); sheet.write("C26", wacc, pct_fmt); sheet.write("D26", wacc - 0.015, pct_fmt)
        sheet.write("A27", "Operating Margin Assumption")
        sheet.write("B27", margin - 0.03, pct_fmt); sheet.write("C27", margin, pct_fmt); sheet.write("D27", margin + 0.03, pct_fmt)
        sheet.write("A28", "Implied Fair Value")
        sheet.write("B28", bear_val, currency_fmt); sheet.write("C28", intrinsic_val, currency_fmt); sheet.write("D28", bull_val, currency_fmt)
    return output.getvalue()


@st.cache_data(ttl=300, show_spinner=False)
def run_dcf_monte_carlo(eps, growth0, base_op_margin, wacc, term_g, margin, iterations=10000):
    """Vectorised and mirrors calculate_interactive_dcf, so the median lands on the headline value."""
    rng = np.random.default_rng(42)
    w = np.maximum(rng.normal(wacc, 0.01, iterations), term_g + 0.005)
    g = np.maximum(rng.normal(growth0, 0.02, iterations), 0.0)
    m = np.maximum(rng.normal(margin, 0.02, iterations), 0.01)
    yrs = np.arange(1, 6)
    cfs = (eps * m / base_op_margin)[:, None] * (1 + g[:, None]) ** yrs
    tv = cfs[:, -1] * (1 + term_g) / (w - term_g)
    values = (cfs / (1 + w[:, None]) ** yrs).sum(axis=1) + tv / (1 + w) ** 5
    return values, w, g, m


@st.cache_data(ttl=300, show_spinner=False)
def run_price_paths_gbm(mu, sigma, current_price, days=252, simulations=1000):
    """mu/sigma MUST be DAILY statistics (the caller passes 1Y daily returns)."""
    rng = np.random.default_rng(7)
    shocks = rng.standard_normal((days - 1, simulations))
    steps = np.exp((mu - 0.5 * sigma ** 2) + sigma * shocks)
    paths = np.vstack([np.full(simulations, current_price), current_price * np.cumprod(steps, axis=0)])
    return paths


# ==========================================
# 5. RISK & QUALITY METRICS
# ==========================================
def _row(df, *names):
    """First matching row of a yfinance statement as a numeric Series, newest period first."""
    if df is None or getattr(df, "empty", True):
        return None
    lookup = {str(i).replace(" ", "").lower(): i for i in df.index}
    for name in names:
        key = name.replace(" ", "").lower()
        if key in lookup:
            s = pd.to_numeric(df.loc[lookup[key]], errors="coerce").dropna()
            if not s.empty:
                return s.sort_index(ascending=False)
    return None


def _ttm(quarterly, annual):
    if quarterly is not None and len(quarterly) >= 4:
        return float(quarterly.iloc[:4].sum())
    if annual is not None and len(annual) >= 1:
        return float(annual.iloc[0])
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fundamentals(symbol: str) -> dict:
    t = yf.Ticker(symbol)

    def get(attr):
        try:
            return getattr(t, attr)
        except Exception:
            return None

    try:
        info = t.info or {}
    except Exception:
        info = {}
    q_cf, a_cf = get("quarterly_cashflow"), get("cashflow")
    q_is, a_is = get("quarterly_income_stmt"), get("income_stmt")
    a_bs = get("balance_sheet")

    mcap, ev = num(info.get("marketCap")), num(info.get("enterpriseValue"))

    fcf = _ttm(_row(q_cf, "Free Cash Flow"), _row(a_cf, "Free Cash Flow"))
    if fcf is None:
        fcf = num(info.get("freeCashflow"))
    fcf_yield = fcf / mcap if fcf is not None and mcap else None
    ev_fcf = ev / fcf if fcf and fcf > 0 and ev else None

    ebit = _ttm(_row(q_is, "EBIT", "Operating Income"), _row(a_is, "EBIT", "Operating Income"))
    tax = _row(a_is, "Tax Rate For Calcs")
    tax_rate = float(np.clip(tax.iloc[0], 0.0, 0.35)) if tax is not None else 0.21
    ic = _row(a_bs, "Invested Capital")
    if ic is None:
        debt_s = _row(a_bs, "Total Debt")
        eq_s = _row(a_bs, "Stockholders Equity", "Common Stock Equity")
        cash_s = _row(a_bs, "Cash And Cash Equivalents")
        if debt_s is not None and eq_s is not None:
            ic = (debt_s + eq_s - (cash_s if cash_s is not None else 0)).dropna()
    avg_ic = float(ic.iloc[:2].mean()) if ic is not None and len(ic) else None
    roic = ebit * (1 - tax_rate) / avg_ic if ebit is not None and avg_ic and avg_ic > 0 else None

    debt, cash, ebitda = num(info.get("totalDebt")), num(info.get("totalCash")), num(info.get("ebitda"))
    net_debt = debt - cash if debt is not None and cash is not None else None
    nd_ebitda = net_debt / ebitda if net_debt is not None and ebitda and ebitda > 0 else None
    interest = _ttm(_row(q_is, "Interest Expense"), _row(a_is, "Interest Expense"))
    interest_cov = ebit / abs(interest) if ebit is not None and interest else None

    ni = _row(a_is, "Net Income")
    cfo = _row(a_cf, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
    ta = _row(a_bs, "Total Assets")
    accrual = None
    if ni is not None and cfo is not None and ta is not None:
        avg_ta = float(ta.iloc[:2].mean())
        accrual = (float(ni.iloc[0]) - float(cfo.iloc[0])) / avg_ta if avg_ta else None

    return {"currency": info.get("financialCurrency") or info.get("currency") or "USD",
            "fcf": fcf, "fcf_yield": fcf_yield, "ev_fcf": ev_fcf, "roic": roic, "net_debt": net_debt,
            "nd_ebitda": nd_ebitda, "interest_cov": interest_cov, "accrual": accrual}


def risk_metrics(close: pd.Series, conf: float = 0.95) -> dict:
    r = close.pct_change().dropna()
    if len(r) < 60:
        return {}
    q = np.percentile(r, (1 - conf) * 100)
    tail = r[r <= q]
    z = NormalDist().inv_cdf(1 - conf)
    wealth = (1 + r).cumprod()
    dd = wealth / wealth.cummax() - 1
    trough = dd.idxmin()
    peak = wealth.loc[:trough].idxmax()
    return {"var_hist": -q, "cvar": -tail.mean(), "var_param": -(r.mean() + z * r.std()),
            "max_dd": float(dd.min()), "peak": peak, "trough": trough,
            "recovered": bool((wealth.loc[trough:] >= wealth.loc[peak]).any())}


def render_risk_quality_panel(symbol: str, wacc: float):
    f = fetch_fundamentals(symbol)
    rk = risk_metrics(fetch_daily_closes(symbol))
    cur = f.get("currency", "USD")
    roic = f["roic"]
    spread = roic - wacc if roic is not None else None
    nd = f["net_debt"]
    nd_value = "Net cash" if nd is not None and nd < 0 else mult_str(f["nd_ebitda"])
    nd_sub = big_str(abs(nd), cur) if nd is not None and nd < 0 else (big_str(nd, cur) + " net debt" if nd else "")

    cards = [
        kpi_card("FCF Yield", pct_str(f["fcf_yield"]), f"FCF {big_str(f['fcf'], cur)}" if f["fcf"] else "",
                 tone(f["fcf_yield"], 0.04, 0.0), "TTM Free Cash Flow / Market Cap"),
        kpi_card("EV / FCF", mult_str(f["ev_fcf"]) if f["ev_fcf"] else "n.m.", "EV / TTM FCF", "",
                 "Enterprise Value / TTM Free Cash Flow (n.m. when FCF <= 0)"),
        kpi_card("ROIC", pct_str(roic), f"vs WACC {spread * 100:+.1f} pp" if spread is not None else "",
                 tone(spread, 0.0, 0.0), "EBIT x (1 - tax) / average invested capital; spread uses the WACC slider"),
        kpi_card("Net Debt / EBITDA", nd_value, nd_sub, tone(f["nd_ebitda"], 1.5, 3.5, False), "(Total Debt - Cash) / EBITDA"),
        kpi_card("Interest Coverage", mult_str(f["interest_cov"]), "EBIT / interest expense",
                 tone(f["interest_cov"], 5, 2), "TTM EBIT / TTM interest expense"),
        kpi_card("Accrual Ratio", pct_str(f["accrual"], 1, True), "Sloan; above +10% is a flag",
                 tone(f["accrual"], 0.05, 0.10, False), "(Net income - Operating cash flow) / average total assets"),
    ]
    if rk:
        cards += [
            kpi_card("1-Day VaR 95%", f"{rk['var_hist'] * 100:.2f}%",
                     f"CVaR {rk['cvar'] * 100:.2f}% | Param {rk['var_param'] * 100:.2f}%", "",
                     "Historical 5th-percentile daily return over 3Y; CVaR = mean loss beyond VaR"),
            kpi_card("Max Drawdown (3Y)", pct_str(rk["max_dd"]),
                     f"{rk['peak']:%b %y} to {rk['trough']:%b %y} | {'recovered' if rk['recovered'] else 'open'}",
                     tone(rk["max_dd"], -0.15, -0.35), "Largest peak-to-trough fall of the cumulative return series"),
        ]
    render_kpi_grid(cards)
    st.caption("Source: yfinance (unofficial Yahoo data). N/A means the line item was not reported or not parseable.")


# ==========================================
# 6. TECHNICAL CHART
# ==========================================
# label: (download period, interval, display window). The extra history is a warm-up so SMA200/EMA/MACD
# are valid on the first visible bar; it is trimmed before plotting.
_TF = {
    "1D": ("5d", "5m", None),
    "1W": ("2mo", "30m", pd.Timedelta(days=7)),
    "1M": ("2y", "1d", pd.DateOffset(months=1)),
    "3M": ("2y", "1d", pd.DateOffset(months=3)),
    "6M": ("2y", "1d", pd.DateOffset(months=6)),
    "1Y": ("3y", "1d", pd.DateOffset(years=1)),
    "5Y": ("10y", "1wk", pd.DateOffset(years=5)),
    "Max": ("max", "1mo", None),
}
_BAR_MINUTES = {"1D": 5, "1W": 30}
OVERLAYS = ["Bollinger", "SMA 50", "SMA 200", "EMA 20", "VWAP"]
PANES = ["Volume", "RSI", "MACD", "ATR"]


def add_indicators(df: pd.DataFrame, intraday: bool) -> pd.DataFrame:
    d = df.copy()
    c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
    d["SMA20"] = c.rolling(20).mean()
    sd = c.rolling(20).std()
    d["BB_Up"], d["BB_Low"] = d["SMA20"] + 2 * sd, d["SMA20"] - 2 * sd
    d["SMA50"], d["SMA200"] = c.rolling(50).mean(), c.rolling(200).mean()
    d["EMA20"] = c.ewm(span=20, adjust=False).mean()

    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    d["MACD"], d["MACD_Sig"] = macd, macd.ewm(span=9, adjust=False).mean()
    d["MACD_Hist"] = d["MACD"] - d["MACD_Sig"]

    delta = c.diff()
    ag = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    al = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    d["RSI"] = (100 - 100 / (1 + ag / al.replace(0, np.nan))).where(al != 0, 100.0)

    pc = c.shift()
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    d["ATR"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    tp = (h + l + c) / 3
    if intraday:
        day = d.index.date
        d["VWAP"] = (tp * v).groupby(day).cumsum() / v.groupby(day).cumsum().replace(0, np.nan)
    else:
        d["VWAP"] = (tp * v).rolling(20).sum() / v.rolling(20).sum().replace(0, np.nan)
    return d


@st.cache_data(ttl=300, show_spinner=False)
def load_chart_frame(symbol: str, timeframe: str) -> pd.DataFrame:
    period, interval, window = _TF.get(timeframe, _TF["1Y"])
    raw = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw.dropna(subset=["Open", "High", "Low", "Close"])
    if df.empty:
        return df
    df = add_indicators(df, intraday=timeframe in _BAR_MINUTES)
    if timeframe == "1D":
        df = df[df.index.date == df.index[-1].date()]
    elif window is not None:
        df = df[df.index >= df.index[-1] - window]
    return df


def _rangebreaks(df, timeframe):
    """Hide weekends/holidays/overnight so candles are contiguous instead of gappy."""
    idx = df.index.tz_localize(None) if df.index.tz is not None else df.index
    if timeframe in _BAR_MINUTES:
        hours = idx.hour + idx.minute / 60
        end, start = float(hours.max()) + _BAR_MINUTES[timeframe] / 60, float(hours.min())
        rb = [dict(bounds=["sat", "mon"])]
        if start > 0 or end < 24:
            rb.append(dict(bounds=[end, start], pattern="hour"))
        return rb
    if timeframe in ("5Y", "Max"):
        return []
    full = pd.bdate_range(idx[0].normalize(), idx[-1].normalize())
    missing = full.difference(idx.normalize())
    rb = [dict(bounds=["sat", "mon"])]
    if len(missing):
        rb.append(dict(values=missing.strftime("%Y-%m-%d").tolist()))
    return rb


def chart_controls() -> dict:
    c1, c2, c3 = st.columns([1.1, 2.4, 2.4])
    style = c1.segmented_control("Chart", ["Candles", "Line"], default="Candles", key="ui_chart_style")
    scale = c1.segmented_control("Scale", ["Linear", "Log"], default="Linear", key="ui_chart_scale")
    overlays = c2.pills("Overlays", OVERLAYS, selection_mode="multi",
                        default=["Bollinger", "SMA 50", "SMA 200"], key="ui_overlays")
    panes = c3.pills("Panes", PANES, selection_mode="multi", default=["Volume", "RSI"], key="ui_panes")
    return {"style": style or "Candles", "log": scale == "Log",
            "overlays": list(overlays or []), "panes": list(panes or [])}


def build_technical_chart(df, timeframe, opts):
    panes = [p for p in PANES if p in opts["panes"]]
    weights = [3] + [1] * len(panes)
    fig = make_subplots(rows=1 + len(panes), cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[w / sum(weights) for w in weights])

    if opts["style"] == "Line":
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="Close", line=dict(color=BLUE, width=2)), row=1, col=1)
    else:
        fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
                                     name="Price", increasing_line_color=GREEN, decreasing_line_color=RED), row=1, col=1)

    def line(col, name, color, row=1, width=1.5, dash=None):
        if col in df and df[col].notna().any():
            fig.add_trace(go.Scatter(x=df.index, y=df[col], name=name,
                                     line=dict(color=color, width=width, dash=dash)), row=row, col=1)

    if "Bollinger" in opts["overlays"] and df["BB_Up"].notna().any():
        edge = "rgba(173,216,230,0.4)"
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_Up"], name="BB Upper", line=dict(color=edge, width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_Low"], name="BB Lower", line=dict(color=edge, width=1),
                                 fill="tonexty", fillcolor="rgba(173,216,230,0.10)"), row=1, col=1)
    if "SMA 50" in opts["overlays"]:
        line("SMA50", "SMA 50", BLUE)
    if "SMA 200" in opts["overlays"]:
        line("SMA200", "SMA 200", "#cfd8dc")
    if "EMA 20" in opts["overlays"]:
        line("EMA20", "EMA 20", AMBER)
    if "VWAP" in opts["overlays"]:
        line("VWAP", "VWAP", "#b388ff", dash="dot")

    for i, pane in enumerate(panes, start=2):
        if pane == "Volume":
            colors = np.where(df["Close"] >= df["Open"], GREEN, RED)
            fig.add_trace(go.Bar(x=df.index, y=df["Volume"], marker_color=colors, opacity=0.45, name="Volume"), row=i, col=1)
        elif pane == "RSI":
            line("RSI", "RSI 14", AMBER, row=i)
            fig.add_hline(y=70, line_dash="dash", line_color=RED, line_width=1, opacity=0.7, row=i, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color=GREEN, line_width=1, opacity=0.7, row=i, col=1)
            fig.update_yaxes(range=[0, 100], row=i, col=1)
        elif pane == "MACD":
            fig.add_trace(go.Bar(x=df.index, y=df["MACD_Hist"], marker_color=np.where(df["MACD_Hist"] >= 0, GREEN, RED),
                                 opacity=0.5, name="MACD Hist"), row=i, col=1)
            line("MACD", "MACD", BLUE, row=i, width=1.3)
            line("MACD_Sig", "Signal", AMBER, row=i, width=1.3)
        elif pane == "ATR":
            line("ATR", "ATR 14", "#b388ff", row=i)
        fig.update_yaxes(title_text=pane, row=i, col=1, showgrid=False)

    if opts["log"]:
        fig.update_yaxes(type="log", row=1, col=1)
    fig.update_xaxes(rangeslider_visible=False, rangebreaks=_rangebreaks(df, timeframe))
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=0, r=0, t=10, b=0), height=max(420, 340 + 130 * len(panes)),
                      hovermode="x unified", legend=dict(orientation="h", y=1.04, x=0))
    return fig


# ==========================================
# 7. CALLBACKS (run before the script reruns, so they may set widget keys)
# ==========================================
def pivot_to(symbol: str):
    st.session_state.search_ticker = symbol


def apply_preset(name: str):
    dm = st.session_state.get("default_margin", 15.0)
    wacc, g, mult = {"Consensus Base": (8.5, 2.5, 1.0), "Recession Shock": (11.0, 1.0, 0.8),
                     "Tech Boom": (7.5, 3.5, 1.2)}[name]
    st.session_state.wacc_pct, st.session_state.g_pct = wacc, g
    st.session_state.margin_pct = float(min(60.0, max(1.0, round(dm * mult, 1))))


# ==========================================
# 8. HEADER & SEARCH
# ==========================================
st.markdown("<h2>⚡ Financial Market Terminal</h2>", unsafe_allow_html=True)
st.text_input("Ticker", key="search_ticker", placeholder="Enter Ticker (e.g., AAPL, MSFT, TSLA)...",
              label_visibility="collapsed")
ticker_input = st.session_state.search_ticker.strip().upper()

if not ticker_input:
    st.info("Please enter a stock ticker in the search bar above to generate the dashboard.")
    st.stop()

info = fetch_info(ticker_input)
if not info:
    st.error(f"Failed to fetch data for '{ticker_input}'. Please check the ticker symbol.")
    st.stop()

current_price = num(info.get("currentPrice")) or num(info.get("regularMarketPrice")) or 0.0
prev_close = num(info.get("previousClose")) or current_price

low_52, high_52 = info.get("fiftyTwoWeekLow"), info.get("fiftyTwoWeekHigh")
range_52 = f"${low_52:.1f} - {high_52:.1f}" if low_52 and high_52 else "N/A"

# Dividend yield: derive from rate/price (fraction-based fields are unambiguous across yfinance versions).
div_rate = num(info.get("dividendRate"))
if div_rate and current_price:
    div_yield_str = f"{div_rate / current_price * 100:.2f}%"
elif num(info.get("trailingAnnualDividendYield")):
    div_yield_str = f"{num(info.get('trailingAnnualDividendYield')) * 100:.2f}%"
else:
    div_yield_str = "0.00% (None)"

beta = info.get("beta")
beta_str = f"{beta:.2f}" if beta is not None else "N/A"

hist_1y = load_chart_frame(ticker_input, "1Y")          # daily bars; used for volatility and the GBM
daily_returns = hist_1y["Close"].pct_change().dropna() if not hist_1y.empty else pd.Series(dtype=float)
vol_str = f"{daily_returns.std() * np.sqrt(252) * 100:.1f}%" if len(daily_returns) > 20 else "N/A"

# DCF slider defaults reset whenever the ticker changes.
_, _base_margin, _ = dcf_inputs(info, current_price)
default_margin = float(min(60.0, max(1.0, round(_base_margin * 100, 1))))
st.session_state.default_margin = default_margin
if st.session_state.get("cfg_ticker") != ticker_input:
    st.session_state.cfg_ticker = ticker_input
    st.session_state.wacc_pct, st.session_state.g_pct, st.session_state.margin_pct = 8.5, 2.5, default_margin


# ==========================================
# 9. DASHBOARD LAYOUT
# ==========================================
top_col1, top_col2 = st.columns([6, 4])

with top_col1:
    st.markdown(f"<h3>{esc(info.get('shortName', ticker_input))} ({esc(ticker_input)})</h3>", unsafe_allow_html=True)

    tf_selected = st.radio("Timeframe", list(_TF.keys()), horizontal=True, index=5)
    hist = load_chart_frame(ticker_input, tf_selected)

    if not hist.empty and tf_selected != "1D":
        ref_price = float(hist["Close"].iloc[0])
    else:
        ref_price = prev_close
    period_change = current_price - ref_price
    period_pct = (period_change / ref_price) * 100 if ref_price else 0.0

    with st.expander("🎛️ Interactive DCF Valuation Assumptions", expanded=False):
        st.caption("Scenario presets")
        pc1, pc2, pc3 = st.columns(3)
        for col, name in zip((pc1, pc2, pc3), ("Consensus Base", "Recession Shock", "Tech Boom")):
            col.button(name, key=f"preset_{name}", on_click=apply_preset, args=(name,))

        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            wacc_val = st.slider("WACC / Discount Rate", 4.0, 16.0, step=0.1, format="%.1f%%", key="wacc_pct") / 100.0
        with sc2:
            term_g_val = st.slider("Terminal Growth Rate (g)", 0.5, 5.0, step=0.1, format="%.1f%%", key="g_pct") / 100.0
        with sc3:
            op_margin_val = st.slider("Operating Margin", 1.0, 60.0, step=0.5, format="%.1f%%", key="margin_pct") / 100.0

        intrinsic_val, projected_cfs, pv_cfs, pv_tv, terminal_value = calculate_interactive_dcf(
            info, current_price, wacc=wacc_val, terminal_g=term_g_val, target_margin=op_margin_val)

        st.download_button(
            label="📥 Export Live DCF Model to Excel",
            data=generate_dcf_excel(ticker_input, current_price, intrinsic_val, wacc_val, term_g_val,
                                    op_margin_val, projected_cfs, terminal_value, info),
            file_name=f"{ticker_input}_DCF_Model.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    dcf_upside = ((intrinsic_val - current_price) / current_price) * 100 if current_price else 0.0
    eps_now = num(info.get("trailingEps"))
    mcap = num(info.get("marketCap"))

    render_kpi_grid([
        kpi_card("Current Price", f"${current_price:.2f}", f"{period_change:+.2f} ({period_pct:+.2f}%)",
                 "pos" if period_change >= 0 else "neg"),
        kpi_card("Intrinsic Value (DCF)", f"${intrinsic_val:.2f}", f"{dcf_upside:+.1f}% vs Price",
                 "pos" if dcf_upside >= 0 else "neg", "5-year per-share earnings DCF with Gordon-growth terminal value"),
        kpi_card("52-Week Range", range_52),
        kpi_card("Market Cap", f"${mcap / 1e9:.2f}B" if mcap else "N/A"),
        kpi_card("Trailing EPS", f"${eps_now:.2f}" if eps_now is not None else "N/A"),
        kpi_card("Dividend Yield", div_yield_str),
        kpi_card("LT Growth (g)", f"{term_g_val * 100:.1f}%", "Tuned (slider)"),
        kpi_card("Volatility (Ann.)", vol_str, f"Beta: {beta_str}", "", "Std. dev. of 1Y daily returns x sqrt(252)"),
    ])

    opts = chart_controls()
    if hist.empty:
        st.warning("No price data returned for this timeframe.")
    else:
        st.plotly_chart(build_technical_chart(hist, tf_selected, opts), key=f"tech_chart_{tf_selected}")
        st.caption("Indicator windows are measured in bars of the selected interval "
                   "(e.g. SMA 50 on 30-minute bars = 50 half-hours).")

    st.markdown("<h4>Risk & Quality</h4>", unsafe_allow_html=True)
    render_risk_quality_panel(ticker_input, wacc=wacc_val)

with top_col2:
    # ---------- Peer comparison ----------
    with st.container(border=True, key="peer_card"):
        st.markdown("<h4>Interactive Peer Comparison</h4>", unsafe_allow_html=True)
        st.markdown("<p style='color:#8a99a8; font-size: 13px; margin-bottom:10px;'>"
                    "Click a ticker to reload the terminal, or type your own peers below.</p>", unsafe_allow_html=True)

        raw_peers = st.text_input("Custom peers", key="custom_peers", placeholder="e.g. AMD, INTC, QCOM (max 6)",
                                  label_visibility="collapsed")
        custom = [p.strip().upper() for p in raw_peers.replace(";", ",").split(",") if p.strip()]
        custom = [p for p in dict.fromkeys(custom) if p != ticker_input][:6]
        peers = custom if custom else get_dynamic_peers(ticker_input, info)

        peer_rows = [{"Ticker": ticker_input, "pe": num(info.get("trailingPE")), "fpe": num(info.get("forwardPE")),
                      "pb": num(info.get("priceToBook")), "om": num(info.get("operatingMargins")),
                      "roe": num(info.get("returnOnEquity"))}] + fetch_peer_metrics(tuple(peers))

        def fx(v, d=1):
            return "N/A" if v is None else f"{v:.{d}f}"

        def fp(v):
            return "N/A" if v is None else f"{v * 100:.1f}%"

        widths = [1.5, 1, 1, 1, 1, 1]
        for c, label in zip(st.columns(widths), ["Ticker", "P/E", "Fwd P/E", "P/B", "Margin", "ROE"]):
            c.markdown(f"<div class='peer-header'>{label}</div>", unsafe_allow_html=True)

        for row in peer_rows:
            rc = st.columns(widths)
            rc[0].button(row["Ticker"], key=f"peer_{row['Ticker']}", on_click=pivot_to, args=(row["Ticker"],),
                         use_container_width=True)
            for c, text in zip(rc[1:], [fx(row["pe"]), fx(row["fpe"]), fx(row["pb"], 2), fp(row["om"]), fp(row["roe"])]):
                c.markdown(f"<div class='peer-cell'>{text}</div>", unsafe_allow_html=True)

        target_pe = peer_rows[0]["pe"]
        peer_pes = [r["pe"] for r in peer_rows[1:] if r["pe"]]
        median_pe = float(np.median(peer_pes)) if peer_pes else None
        if median_pe and target_pe:
            if target_pe < median_pe * 0.9:
                callout = "<span style='color:#00e676;'>Undervalued (Cheap)</span>"
            elif target_pe > median_pe * 1.1:
                callout = "<span style='color:#ff3d57;'>Overvalued (Expensive)</span>"
            else:
                callout = "<span style='color:#1e88e5;'>Fairly Valued</span>"
            st.markdown(f"<br>**Relative Valuation Signal:** {callout} vs Peer Median P/E", unsafe_allow_html=True)

    # ---------- Monte Carlo ----------
    with st.container(border=True, key="mc_card"):
        st.markdown("<h4>Monte Carlo Simulation (10k Iters)</h4>", unsafe_allow_html=True)
        eps_mc, base_op, growth_mc = dcf_inputs(info, current_price)
        sim_values, wacc_dist, g_dist, m_dist = run_dcf_monte_carlo(
            eps_mc, growth_mc, base_op, wacc_val, term_g_val, op_margin_val)
        p10, p50, p90 = np.percentile(sim_values, [10, 50, 90])

        sim_view = st.pills("Simulation View", ["Bell Curve", "Tornado Diagram", "Spaghetti Plot", "Fan Chart"],
                            default="Spaghetti Plot") or "Spaghetti Plot"
        layout_kw = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         height=230, margin=dict(l=0, r=0, t=10, b=0), showlegend=False)

        if sim_view == "Bell Curve":
            fig_mc = px.histogram(x=sim_values, nbins=100, color_discrete_sequence=[BLUE])
            fig_mc.add_vline(x=p10, line_dash="dash", line_color=RED, annotation_text="Bear")
            fig_mc.add_vline(x=p50, line_dash="solid", line_color="#ffffff", annotation_text="Base")
            fig_mc.add_vline(x=p90, line_dash="dash", line_color=GREEN, annotation_text="Bull")
            fig_mc.update_layout(xaxis_title="Simulated Intrinsic Value ($)", yaxis_title="Frequency", **layout_kw)
            st.plotly_chart(fig_mc, key="mc_bell")

        elif sim_view == "Tornado Diagram":
            sens_df = pd.DataFrame({
                "Variable": ["WACC", "Revenue Growth", "Operating Margin"],
                "Impact Coefficient": [np.corrcoef(wacc_dist, sim_values)[0, 1],
                                       np.corrcoef(g_dist, sim_values)[0, 1],
                                       np.corrcoef(m_dist, sim_values)[0, 1]]})
            sens_df = sens_df.reindex(sens_df["Impact Coefficient"].abs().sort_values().index)
            fig_t = px.bar(sens_df, x="Impact Coefficient", y="Variable", orientation="h",
                           color="Impact Coefficient", color_continuous_scale=[RED, "#131f33", GREEN])
            fig_t.update_layout(coloraxis_showscale=False, **layout_kw)
            st.plotly_chart(fig_t, key="mc_tornado")

        else:
            if daily_returns.empty or current_price <= 0:
                st.info("Not enough daily price history for a price-path simulation.")
            else:
                paths = run_price_paths_gbm(float(daily_returns.mean()), float(daily_returns.std()), current_price)
                fig_p = go.Figure()
                if sim_view == "Spaghetti Plot":
                    palette = px.colors.qualitative.Light24 + px.colors.qualitative.Alphabet
                    for i in range(100):
                        fig_p.add_trace(go.Scatter(y=paths[:, i], mode="lines", opacity=0.4,
                                                   line=dict(width=1.5, color=palette[i % len(palette)]), showlegend=False))
                    fig_p.add_trace(go.Scatter(y=np.median(paths, axis=1), mode="lines",
                                               line=dict(width=3.5, color="#ffffff"), name="Median Path"))
                else:
                    q = np.percentile(paths, [5, 25, 50, 75, 95], axis=1)
                    x = np.arange(paths.shape[0])
                    for hi, lo, fill in ((4, 0, "rgba(30,136,229,0.15)"), (3, 1, "rgba(30,136,229,0.30)")):
                        fig_p.add_trace(go.Scatter(x=x, y=q[hi], line=dict(width=0), hoverinfo="skip", showlegend=False))
                        fig_p.add_trace(go.Scatter(x=x, y=q[lo], line=dict(width=0), fill="tonexty",
                                                   fillcolor=fill, hoverinfo="skip", showlegend=False))
                    fig_p.add_trace(go.Scatter(x=x, y=q[2], mode="lines", line=dict(width=3, color="#ffffff"), name="Median"))
                fig_p.update_layout(xaxis_title="Trading Days in Future", yaxis_title="Simulated Price ($)", **layout_kw)
                st.plotly_chart(fig_p, key="mc_paths")
                st.caption("Price paths use mean and volatility of the last year of daily returns.")

        st.markdown(f"""
<table style="width:100%; text-align:center; border:1px solid #1e3252;">
<tr style="background-color:#1e3252;"><th>Bearish (10th)</th><th>Median (50th)</th><th>Bullish (90th)</th></tr>
<tr><td>&#36;{p10:.2f}</td><td style="color:#1e88e5; font-weight:bold;">&#36;{p50:.2f}</td><td>&#36;{p90:.2f}</td></tr>
</table>""", unsafe_allow_html=True)


# ==========================================
# 10. LOWER SECTION: NEWS
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
            hours_ago = max(0, int((datetime.now().timestamp() - item["published"]) / 3600))
            if hours_ago < 1:
                time_str = "Just now"
            elif hours_ago < 24:
                time_str = f"{hours_ago}h ago"
            else:
                time_str = f"{hours_ago // 24}d ago"

            sentiment, badge_class = get_sentiment(item["title"])
            link = html.escape(item["link"], quote=True)
            st.markdown(
                '<div style="background-color:#131f33; padding:15px; border-radius:8px; border:1px solid #1e3252; '
                'margin-bottom:15px; height:160px; overflow:hidden;">'
                '<div style="display:flex; justify-content:space-between; margin-bottom:10px;">'
                f'<span style="color:#8a99a8; font-size:12px; font-weight:bold;">📰 {esc(item["publisher"][:15])} • {time_str}</span>'
                f'<span class="{badge_class}">{sentiment}</span></div>'
                f'<a href="{link}" target="_blank" rel="noopener noreferrer" '
                'style="color:#ffffff; text-decoration:none; font-weight:bold; font-size:14px; line-height:1.4;">'
                f'{esc(item["title"])}</a></div>',
                unsafe_allow_html=True)
