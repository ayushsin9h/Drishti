"""ParkSight — Parking-Induced Congestion Intelligence for Bengaluru.

Serving layer: reads only the small precomputed artifacts in data/processed/.
Run locally:   streamlit run app.py
"""
import io
import re
import json
import hashlib
from datetime import datetime
from pathlib import Path

import pandas as pd
import pydeck as pdk
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

try:
    from streamlit_option_menu import option_menu
    HAS_MENU = True
except Exception:
    HAS_MENU = False
try:
    from streamlit_mic_recorder import speech_to_text
    HAS_MIC = True
except Exception:
    HAS_MIC = False
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except Exception:
    HAS_AUTOREFRESH = False

# Make this folder importable no matter where the app is launched from
# (fixes "ModuleNotFoundError: No module named 'src'" on some setups).
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.i18n import LANGS, SPEECH_LANG, t, build_area_vocab, resolve_area
from src import ops
import time as _time

ROOT = Path(__file__).resolve().parent
PROC = ROOT / "data" / "processed"
VIOLET = "#8B5CF6"
GOLD = "#D4AF37"
DONUT_COLORS = ["#8B5CF6", "#22D3EE", "#EC4899", "#6366F1", "#0EA5E9",
                "#F472B6", "#A855F7", "#34D399", "#FB7185", "#818CF8"]

# ---- demo-grade login (self-contained, no fragile dependency) ----
# NOTE: demonstration auth — credentials are shown on the login screen so judges
# can always get in. Production would use a real identity provider. To DISABLE
# the login entirely, comment out the `require_login()` call below.
_USERS = {"admin": "Traffic Admin (BTP)", "officer": "Patrol Officer"}
_PW = {"admin": hashlib.sha256(b"admin123").hexdigest(),
       "officer": hashlib.sha256(b"officer123").hexdigest()}


def require_login():
    if st.session_state.get("authed"):
        return
    # keep the session logged in across theme-switch page reloads (demo only)
    if st.query_params.get("auth") == "1":
        st.session_state.authed = True
        st.session_state.user = "Traffic Admin (BTP)"
        return
    st.markdown(
        "<div style='background:linear-gradient(135deg,#7C3AED,#EC4899);"
        "border-radius:18px;padding:26px 30px;color:#fff;margin-bottom:20px;'>"
        "<div style='font-size:2rem;font-weight:800;'>दृष्टि — DRISHTI</div>"
        "<div style='opacity:0.92;margin-top:4px;'>Digital Real-time Intelligence for "
        "Smart Hotspot &amp; Traffic Insights · हर सड़क पर नज़र, हर सफ़र आसान</div></div>",
        unsafe_allow_html=True)
    st.subheader("🔐 Secure sign-in")
    with st.form("login_form"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        ok = st.form_submit_button("Sign in")
    if ok:
        if u in _PW and _PW[u] == hashlib.sha256(p.encode()).hexdigest():
            st.session_state.authed = True
            st.session_state.user = _USERS[u]
            st.query_params["auth"] = "1"
            st.rerun()
        st.error("Invalid username or password.")
    st.caption("Demo credentials — sign in with either account:")
    st.table(pd.DataFrame(
        {"USERNAME": ["admin", "officer"], "PASSWORD": ["admin123", "officer123"]}
    ).set_index("USERNAME"))
    st.stop()

# sidebar starts open so the nav is always visible
st.set_page_config(page_title="DRISHTI · Bengaluru", page_icon="🚦",
                   layout="wide", initial_sidebar_state="expanded")


# ---------------- data ----------------
@st.cache_data
def load():
    hot = pd.read_parquet(PROC / "hotspots.parquet")
    fc = pd.read_parquet(PROC / "forecast.parquet")
    off = pd.read_parquet(PROC / "offenders.parquet")
    meta = json.loads((PROC / "meta.json").read_text(encoding="utf-8"))
    fc = fc.merge(hot[["h3", "location", "junction_name", "cii"]], on="h3", how="left")
    return hot, fc, off, meta


@st.cache_data
def load_trends():
    return pd.read_parquet(PROC / "trends.parquet")


@st.cache_data
def load_byday():
    return pd.read_parquet(PROC / "trends_byday.parquet")


def cii_color(cii):
    x = max(0.0, min(1.0, cii / 100.0))
    g, y, r = (22, 163, 74), (245, 158, 11), (220, 38, 38)
    if x < 0.5:
        f, a, b = x / 0.5, g, y
    else:
        f, a, b = (x - 0.5) / 0.5, y, r
    return [int(a[i] + (b[i] - a[i]) * f) for i in range(3)] + [185]


def cii_to_hex(c):
    r, g, b, _ = cii_color(c)
    return f"rgb({r},{g},{b})"


# ---------------- theme CSS (theme-AGNOSTIC: adapts to light & dark) ----------------
def inject_css():
    # No hardcoded background/text colours -> the native Light/Dark theme (⋮ menu)
    # stays fully consistent, including tables. Only shape + accent + font here.
    st.markdown("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
      html, body, [class*="css"], .stApp { font-family:'Plus Jakarta Sans',sans-serif; }
      /* translucent violet glow works over both dark and light backgrounds */
      .stApp { background-image:
        radial-gradient(1000px 520px at 80% -10%, rgba(124,77,255,0.16), transparent 60%); }
      footer { visibility:hidden; }          /* keep the header so the ⋮ menu + sidebar toggle work */
      .block-container { padding-top:1.6rem; }
      h1,h2,h3,h4 { font-weight:700; letter-spacing:-0.01em; }
      [data-testid="stMetric"] {
        background:rgba(212,175,55,0.07); border:1px solid rgba(212,175,55,0.45);
        border-radius:16px; padding:16px 18px;
        box-shadow:0 8px 30px rgba(160,120,20,0.10); backdrop-filter:blur(8px); }
      .stButton button, .stDownloadButton button {
        background:linear-gradient(135deg,#7C3AED,#A855F7); color:#fff;
        border:none; border-radius:10px; font-weight:600; }
      .stTextInput input, [data-baseweb="select"] > div {
        border:1px solid rgba(139,92,246,0.35) !important; border-radius:10px; }
      .stTextInput input { padding:0.55rem 0.75rem; font-size:0.95rem; }
    </style>""", unsafe_allow_html=True)


# ---------------- voice ----------------
def play_tts(text, lang_code):
    """Reliable, multilingual TTS via gTTS (plays an MP3). Browser fallback if offline."""
    try:
        from gtts import gTTS
        buf = io.BytesIO()
        gTTS(text=text, lang=lang_code).write_to_fp(buf)
        st.audio(buf.getvalue(), format="audio/mp3", autoplay=True)
        return True
    except Exception:
        loc = {"en": "en-IN", "hi": "hi-IN", "kn": "kn-IN"}.get(lang_code, "en-IN")
        safe = json.dumps(text)
        components.html(f"""<script>
            const u=new SpeechSynthesisUtterance({safe});u.lang="{loc}";
            window.speechSynthesis.cancel();window.speechSynthesis.speak(u);</script>""",
                        height=0)
        return False


def parse_command(text):
    low = (text or "").lower().strip()
    out = {"speak": any(w in low for w in ["read", "speak", "say", "aloud", "tell",
                                           "ಮಾತ", "ಓದ", "बोल", "पढ"])}
    # which language to SPEAK the answer in (overrides the UI language)
    if any(w in low for w in ["hindi", "हिंदी", "हिन्दी", "हिंदी में"]):
        out["say_lang"] = "hi"
    elif any(w in low for w in ["kannada", "ಕನ್ನಡ", "kannad"]):
        out["say_lang"] = "kn"
    elif "english" in low:
        out["say_lang"] = "en"
    m = re.search(r"(?:top|ಮೇಲಿನ|शीर्ष)\s*(\d+)", low)
    if m:
        out["topn"] = max(5, min(50, int(m.group(1))))
    if any(w in low for w in ["worst", "high impact", "critical", "severe",
                              "ಕೆಟ್ಟ", "खराब", "गंभीर"]):
        out["min_cii"] = 80
    return out


def speak_summary(rows, say_lang, n):
    """Build a spoken summary of the top-n zones in the requested language."""
    rows = rows.head(n)
    if say_lang == "hi":
        parts = [f"शीर्ष {len(rows)} क्षेत्र।"]
        for i, (_, r) in enumerate(rows.iterrows(), 1):
            parts.append(f"{i}. {r['location'].split(',')[0]}, "
                         f"सी आई आई {r['cii']:.0f}, {int(r['n_violations'])} उल्लंघन।")
        return " ".join(parts)
    if say_lang == "kn":
        parts = [f"ಮೇಲಿನ {len(rows)} ಪ್ರದೇಶಗಳು."]
        for i, (_, r) in enumerate(rows.iterrows(), 1):
            parts.append(f"{i}. {r['location'].split(',')[0]}, "
                         f"ಸಿ ಐ ಐ {r['cii']:.0f}, {int(r['n_violations'])} ಉಲ್ಲಂಘನೆ.")
        return " ".join(parts)
    nums = ["one", "two", "three", "four", "five", "six", "seven", "eight"]
    parts = [f"Top {len(rows)} zones."]
    for i, (_, r) in enumerate(rows.iterrows()):
        label = nums[i] if i < len(nums) else str(i + 1)
        parts.append(f"{label}: {r['location'].split(',')[0]}, "
                     f"C I I {r['cii']:.0f}, {int(r['n_violations'])} violations.")
    return " ".join(parts)


# ---------------- plotly helpers (let theme="streamlit" adapt to light/dark) ----------------
def _layout(fig, height=240, title=None):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=36 if title else 8, b=8),
                      title=dict(text=title, font=dict(size=14)) if title else None,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      showlegend=False)
    return fig


def line_chart(daily, title, mark_last=False):
    fig = go.Figure(go.Scatter(x=daily["label"], y=daily["value"], mode="lines",
                               line=dict(color=VIOLET, width=2.5), fill="tozeroy",
                               fillcolor="rgba(139,92,246,0.22)"))
    if mark_last and len(daily):
        row = daily.iloc[-1]
        fig.add_trace(go.Scatter(x=[row["label"]], y=[row["value"]], mode="markers",
                                 marker=dict(color="#F472B6", size=13)))
    fig.update_xaxes(showgrid=False)
    return _layout(fig, title=title)


def bar_chart(d, title, ramp=False):
    colors = [cii_to_hex(v / (max(d["value"]) or 1) * 100) for v in d["value"]] if ramp else VIOLET
    fig = go.Figure(go.Bar(x=d["label"], y=d["value"], marker_color=colors))
    fig.update_xaxes(showgrid=False)
    return _layout(fig, title=title)


def rainbow_gauge(value, title):
    stops = [(0.0, (34, 211, 238)), (0.4, (52, 211, 153)),
             (0.7, (250, 204, 21)), (1.0, (244, 114, 182))]

    def lerp(tt):
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if tt <= t1:
                f = (tt - t0) / (t1 - t0 + 1e-9)
                return tuple(int(c0[j] + (c1[j] - c0[j]) * f) for j in range(3))
        return stops[-1][1]

    seg = 28
    steps = [{"range": [i / seg * 100, (i + 1) / seg * 100],
              "color": f"rgb{lerp((i + 0.5) / seg)}"} for i in range(seg)]
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value, number={"suffix": "%", "font": {"size": 38}},
        gauge={"axis": {"range": [0, 100], "tickwidth": 0},
               "bar": {"color": "rgba(255,255,255,0)"}, "borderwidth": 0, "steps": steps}))
    return _layout(fig, height=250, title=title)


# ---------------- gradient KPI card + donut ----------------
def sparkline_svg(series, color, w=120, h=36):
    if not series or len(series) < 2:
        return ""
    mn, mx = min(series), max(series)
    rng = (mx - mn) or 1
    pts = " ".join(
        f"{i/(len(series)-1)*w:.1f},{h - (v-mn)/rng*(h-7) - 4:.1f}"
        for i, v in enumerate(series))
    last = pts.split()[-1]
    return (f"<svg width='{w}' height='{h}' viewBox='0 0 {w} {h}' "
            f"preserveAspectRatio='none'><polyline points='{pts}' fill='none' "
            f"stroke='{color}' stroke-width='2' stroke-linecap='round' "
            f"stroke-linejoin='round'/><circle cx='{last.split(',')[0]}' "
            f"cy='{last.split(',')[1]}' r='2.6' fill='{color}'/></svg>")


def bars_svg(vals, colors, w=120, h=36):
    mx = max(vals) or 1
    bw = w / (len(vals) * 1.7)
    gap = bw * 0.7
    rects = "".join(
        f"<rect x='{i*(bw+gap)+gap:.1f}' y='{h-(v/mx)*(h-5)-2:.1f}' width='{bw:.1f}' "
        f"height='{(v/mx)*(h-5):.1f}' rx='2' fill='{colors[i]}'/>"
        for i, v in enumerate(vals))
    return f"<svg width='{w}' height='{h}' viewBox='0 0 {w} {h}'>{rects}</svg>"


def _delta(series, lower_is_better=True):
    if not series or len(series) < 14:
        return ""
    k = min(30, len(series) // 2)
    recent = sum(series[-k:]) / k
    prior = sum(series[-2 * k:-k]) / k
    if prior == 0:
        return ""
    pct = (recent - prior) / prior * 100
    up = pct >= 0
    good = (not up) if lower_is_better else up
    color = "#34D399" if good else "#F87171"
    return (f"<span style='color:{color};font-weight:600;'>{'▲' if up else '▼'} "
            f"{abs(pct):.1f}%</span> <span style='opacity:0.55;font-size:0.72rem;'>"
            f"vs prev {k}d</span>")


def kpi_card(icon, label, value, accent=VIOLET, series=None, viz="spark",
             sub=None, lower_is_better=True):
    if viz == "bars" and series:
        chart = bars_svg(series, ["rgba(170,170,190,0.30)", accent])
    elif series:
        chart = sparkline_svg(series, accent)
    else:
        chart = ""
    delta = sub if sub else _delta(series, lower_is_better)
    delta_html = (f"<div style='font-size:0.78rem;margin-top:7px;'>{delta}</div>"
                  if delta else "")
    st.markdown(
        f"<div style='background:rgba(139,92,246,0.06);"
        f"border:1px solid rgba(139,92,246,0.28);border-radius:16px;"
        f"padding:16px 18px;height:152px;box-shadow:0 6px 20px rgba(80,40,160,0.10);'>"
        f"<div style='display:flex;justify-content:space-between;align-items:flex-start;'>"
        f"<div style='width:36px;height:36px;border-radius:10px;background:{accent}26;"
        f"display:flex;align-items:center;justify-content:center;font-size:18px;'>{icon}</div>"
        f"<div>{chart}</div></div>"
        f"<div style='font-size:0.82rem;opacity:0.7;margin-top:10px;'>{label}</div>"
        f"<div style='font-size:1.9rem;font-weight:800;line-height:1.1;'>{value}</div>"
        f"{delta_html}</div>", unsafe_allow_html=True)


def donut(labels, values, title):
    fig = go.Figure(go.Pie(labels=list(labels), values=list(values), hole=0.62,
                           marker=dict(colors=DONUT_COLORS), textinfo="percent",
                           textfont=dict(color="#fff", size=12), sort=True))
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=42, b=10),
                      title=dict(text=title, font=dict(size=14)),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="v", x=1, y=0.5, font=dict(size=11)))
    return fig


def active_theme():
    """Active theme ('light'/'dark'); defaults to dark on first run / older Streamlit."""
    try:
        tp = st.context.theme.type
        return tp if tp in ("light", "dark") else "dark"
    except Exception:
        return "dark"


def theme_css(mode):
    """Light / system overrides layered on top of the dark default.
    No !important on text colours, so inline-coloured bits (logo, KPI accents,
    status cards) keep their colours; only the *defaults* get recoloured."""
    light = """
      .stApp { background-color:#F6F3FF; }
      .stApp p, .stApp li, .stApp label,
      .stApp h1, .stApp h2, .stApp h3, .stApp h4 { color:#241748; }
      [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color:#5f548b; }
      section[data-testid="stSidebar"] > div:first-child { background:#ECE6FB; }
      section[data-testid="stSidebar"], section[data-testid="stSidebar"] p,
      section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] div { color:#2b1d55; }
      [data-testid="stSegmentedControl"] button p { color:#2b1d55; }
      .drishti-sub { color:#2563EB !important; }
    """
    if mode == "light":
        return f"<style>{light}</style>"
    if mode == "system":
        return f"<style>@media (prefers-color-scheme: light) {{{light}}}</style>"
    return ""


# ==================== APP ====================
inject_css()
require_login()        # comment this line out to disable the login gate
hot, fc, off, meta = load()
THEME = active_theme()        # follows the ⋮ menu (top-right) -> Settings -> Theme
ACCENT = "#FACC15" if THEME == "dark" else "#2563EB"   # gold text -> yellow (dark) / blue (light)
MAP_STYLE = "dark" if THEME == "dark" else "light"
NAV_COLOR = "#9B8FC2" if THEME == "dark" else "#4C3A82"
area_vocab = build_area_vocab(hot)
hot["fill"] = hot["cii"].apply(cii_color)
mm = meta["model_metrics"]

NAV_KEYS = ["tab_map", "tab_ops", "tab_trends", "tab_rank", "tab_off", "tab_fc",
            "tab_patrol", "tab_whatif", "tab_event"]
NAV_ICONS = ["geo-alt-fill", "broadcast", "graph-up", "list-check",
             "exclamation-triangle-fill", "magic",
             "signpost-split-fill", "sliders", "calendar-event-fill"]

with st.sidebar:
    st.markdown(
        "<div style='display:flex;align-items:center;gap:11px;margin:2px 0 14px 0;'>"
        "<div style='width:42px;height:42px;border-radius:12px;"
        "background:linear-gradient(135deg,#7C3AED,#EC4899);color:#fff;font-weight:800;"
        "font-size:23px;display:flex;align-items:center;justify-content:center;"
        "box-shadow:0 4px 16px rgba(124,77,255,0.45);'>D</div>"
        "<div><div style='font-weight:800;font-size:1.18rem;line-height:1.05;'>DRISHTI</div>"
        "<div style='font-size:0.7rem;opacity:0.6;letter-spacing:0.02em;'>"
        "दृष्टि · Bengaluru Traffic Police</div></div></div>",
        unsafe_allow_html=True)
    if st.session_state.get("user"):
        lo1, lo2 = st.columns([2, 1])
        lo1.markdown(
            f"<div style='background:rgba(139,92,246,0.12);border-radius:10px;"
            f"padding:7px 11px;font-size:0.82rem;'>👤 <b>{st.session_state['user']}</b>"
            f"</div>", unsafe_allow_html=True)
        if lo2.button("Log out", use_container_width=True):
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    lang_label = st.selectbox("🌐 " + t("language", "en"), list(LANGS.keys()))
    lang = LANGS[lang_label]
    st.markdown("<div style='font-size:0.7rem;font-weight:700;letter-spacing:0.08em;"
                "opacity:0.45;margin:10px 0 2px 2px;'>NAVIGATION</div>",
                unsafe_allow_html=True)
    labels = [re.sub(r"^[^\w]+", "", t(k, lang)).strip() for k in NAV_KEYS]
    if HAS_MENU:
        choice = option_menu(
            None, labels, icons=NAV_ICONS, default_index=0,
            styles={"container": {"background-color": "transparent", "padding": "2px 0"},
                    "icon": {"color": NAV_COLOR, "font-size": "15px"},
                    "nav-link": {"color": NAV_COLOR, "font-size": "14px",
                                 "border-radius": "10px", "margin": "3px 0",
                                 "--hover-color": "rgba(139,92,246,0.15)"},
                    "nav-link-selected": {"background-color": VIOLET, "color": "#fff",
                                          "font-weight": "600"}})
    else:
        st.caption("⚠️ run `pip install -r requirements.txt` for the icon nav")
        choice = st.radio("Navigate", labels, label_visibility="collapsed")
    section = NAV_KEYS[labels.index(choice)]

    st.divider()
    if "history" not in st.session_state:
        st.session_state.history = []
    st.markdown("**" + t("history", lang) + "**")
    if st.session_state.history:
        for h in reversed(st.session_state.history[-8:]):
            st.caption(f"• {h['q']}  _( {h['t']} )_")
        if st.button(t("clear_history", lang)):
            st.session_state.history = []
            st.rerun()
    else:
        st.caption(t("no_history", lang))
    st.markdown(
        f"<div style='margin-top:14px;background:rgba(52,211,153,0.10);"
        f"border:1px solid rgba(52,211,153,0.3);border-radius:12px;padding:10px 12px;"
        f"font-size:0.76rem;'>🟢 <b>Live</b> · {meta['n_cells']:,} zones monitored<br>"
        f"<span style='opacity:0.65;'>Forecast MAE {mm['valid_mae']} · "
        f"↓{mm.get('improvement_pct','')}% vs baseline</span></div>",
        unsafe_allow_html=True)
    st.divider()
    st.markdown("<div style='font-size:0.72rem;font-weight:700;letter-spacing:0.06em;"
                "opacity:0.5;margin:4px 0 2px 2px;'>🎨 THEME</div>", unsafe_allow_html=True)
    st.caption("Switch theme via the ⋮ menu (top-right) → Settings → Theme.")

# ----- header + KPIs (always) -----
st.markdown(
    "<h1 style='line-height:1.55;margin:0 0 2px 0;padding-top:0.14em;font-size:2.55rem;"
    "font-weight:800;letter-spacing:-0.01em;'>दृष्टि — DRISHTI</h1>",
    unsafe_allow_html=True)
st.markdown(
    f"<div class='drishti-sub' style='color:{ACCENT};font-weight:600;font-size:1.02rem;'>"
    "Digital Real-time Intelligence for Smart Hotspot &amp; Traffic Insights</div>",
    unsafe_allow_html=True)
st.caption("हर सड़क पर नज़र, हर सफ़र आसान  ·  Bengaluru Traffic Police")

# ----- command / voice bar (top of content, prominent) -----
_mic_ready = "🎤 ready" if HAS_MIC else "⚠️ mic component missing"
st.markdown(
    "<div style='display:flex;align-items:center;gap:10px;margin:16px 0 8px 0;'>"
    "<div style='width:32px;height:32px;border-radius:10px;flex:none;"
    "background:linear-gradient(135deg,#7C3AED,#EC4899);display:flex;align-items:center;"
    "justify-content:center;font-size:16px;box-shadow:0 3px 12px rgba(124,77,255,.4);'>🎙️</div>"
    f"<div style='font-weight:700;font-size:1.04rem;'>{t('voice_nav', lang)}</div>"
    "<div style='flex:1;'></div>"
    f"<div style='font-size:0.72rem;opacity:.6;white-space:nowrap;'>{_mic_ready}"
    "  ·  🔊 EN · ಕನ್ನಡ · हिन्दी</div></div>", unsafe_allow_html=True)
cb1, cb2 = st.columns([6, 1])
with cb1:
    typed = st.text_input(t("ask", lang), placeholder="🔍  " + t("placeholder", lang),
                          label_visibility="collapsed")
spoken = None
with cb2:
    if HAS_MIC:
        spoken = speech_to_text(language=SPEECH_LANG.get(lang, "en-IN"),
                                start_prompt="🎤", stop_prompt="⏹",
                                just_once=True, use_container_width=True, key="stt")

query = spoken or typed
if query:
    cmd = parse_command(query)
    res = hot.copy()
    area = resolve_area(query, lang, area_vocab)
    if area:
        res = res[res["location"].str.contains(re.escape(area), case=False, na=False)]
    if "min_cii" in cmd:
        res = res[res["cii"] >= cmd["min_cii"]]
    res = res.head(cmd.get("topn", 10))
    st.session_state.history.append(
        {"q": query, "t": datetime.now().strftime("%H:%M"), "lang": lang,
         "area": area or "", "results": len(res)})
    tag = f" → {area}" if area else ""
    st.markdown(f"**{t('understood', lang)}:** _{query}_{tag} ({len(res)})")
    st.dataframe(res[["cii_rank", "cii", "location", "junction_name", "n_violations",
                      "top_violation"]].rename(columns={
        "cii_rank": "Rank", "cii": "CII", "location": "Location",
        "junction_name": "Junction", "n_violations": "Violations",
        "top_violation": "Top violation"}), use_container_width=True, hide_index=True)
    if len(res):
        say_lang = cmd.get("say_lang", lang)        # query language overrides UI language
        speak_n = min(len(res), cmd.get("topn", 3), 8)
        summary = speak_summary(res, say_lang, speak_n)
        lang_name = {"en": "English", "hi": "Hindi", "kn": "Kannada"}[say_lang]
        if cmd.get("speak"):
            play_tts(summary, say_lang)
        if st.button(f"🔊 Read aloud ({lang_name})", key="read_btn"):
            play_tts(summary, say_lang)
st.write("")

sp = meta.get("kpi_sparks", {})
kc = st.columns(4)
with kc[0]:
    kpi_card("🚗", t("kpi_violations", lang), f"{meta['n_records']:,}",
             accent="#8B5CF6", series=sp.get("violations"))
with kc[1]:
    kpi_card("📍", t("kpi_zones", lang), f"{meta['n_cells']:,}",
             accent="#22D3EE", series=sp.get("zones"))
with kc[2]:
    kpi_card("🔥", t("kpi_high", lang), f"{int((hot.cii >= 70).sum()):,}",
             accent=ACCENT, series=sp.get("peak"))
with kc[3]:
    bl = mm.get("baseline_lag7_mae", 1.0)
    kpi_card("🎯", t("kpi_mae", lang), mm["valid_mae"], accent="#34D399",
             series=[bl, mm["valid_mae"]], viz="bars",
             sub=(f"<span style='color:#34D399;font-weight:600;'>↓ "
                  f"{mm['improvement_pct']}% vs baseline</span>"
                  if mm.get("improvement_pct") else None))
st.write("")
st.divider()

# ==================== sections ====================
if section == "tab_map":
    mc1, mc2 = st.columns([1.1, 2.6])
    with mc1:
        min_cii = st.slider(t("min_cii", lang), 0, 100, 50, 5)
    view = hot[hot.cii >= min_cii]
    with mc2:
        st.markdown(
            "<div style='display:flex;align-items:center;gap:12px;padding-top:1.7rem;"
            "flex-wrap:wrap;'>"
            f"<span style='font-size:0.9rem;'>Showing <b>{len(view):,}</b> of "
            f"{len(hot):,} zones</span>"
            "<span style='flex:1;'></span>"
            "<span style='font-size:0.78rem;opacity:.7;'>Low</span>"
            "<div style='width:150px;height:11px;border-radius:6px;"
            "border:1px solid rgba(125,90,200,0.45);background:linear-gradient(90deg,"
            "rgb(22,163,74) 0%,rgb(245,158,11) 50%,rgb(220,38,38) 100%);'></div>"
            "<span style='font-size:0.78rem;opacity:.7;'>High</span>"
            "<span style='font-size:0.76rem;opacity:.55;'>CII 0–100</span></div>",
            unsafe_allow_html=True)
    layer = pdk.Layer("H3HexagonLayer", view, pickable=True, filled=True, extruded=True,
                      get_hexagon="h3", get_fill_color="fill",
                      get_elevation="cii", elevation_scale=8, opacity=0.7)
    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=pdk.ViewState(latitude=12.97, longitude=77.59, zoom=11, pitch=45),
        map_style=MAP_STYLE,
        tooltip={
            "html": "<div style='font-weight:700;font-size:13px;'>CII {cii}"
                    "<span style='opacity:.7;font-weight:500;'> · rank #{cii_rank}</span></div>"
                    "<div style='font-size:11px;opacity:.85;margin-top:1px;'>{location}</div>"
                    "<div style='font-size:11px;margin-top:3px;'><b>{n_violations}</b> "
                    "violations · <b>{active_days}</b> days</div>"
                    "<div style='font-size:11px;'>Top: {top_violation}</div>",
            "style": {"backgroundColor": "rgba(20,12,46,0.94)", "color": "#F4F1FF",
                      "borderRadius": "10px", "padding": "10px 12px", "maxWidth": "250px",
                      "whiteSpace": "normal", "lineHeight": "1.35",
                      "fontFamily": "Plus Jakarta Sans, sans-serif",
                      "border": "1px solid rgba(139,92,246,0.45)",
                      "boxShadow": "0 8px 26px rgba(0,0,0,0.4)"}},
    ), use_container_width=True, height=560, key=f"impactmap_{THEME}")

elif section == "tab_ops":
    st.subheader("🚨 Live operations — congestion alerts & enforcement")
    st.caption("⚠️ Simulated live feed: historical hotspots replayed as real-time alerts. "
               "In production this is driven by live ANPR / e-challan feeds, with push "
               "notifications to field officers and control-room displays.")

    thr = st.slider("Trigger an alert when CII ≥", 50, 100, 75, 5)
    alerts = (hot[hot.cii >= thr].sort_values("cii", ascending=False)
              .head(20).reset_index(drop=True))

    def rec_action(c):
        if c >= 88:
            return "🚨 Deploy patrol + initiate towing"
        if c >= 78:
            return "⚠️ On-spot enforcement / challan drive"
        return "👁 Monitor + advisory signage"
    alerts["Recommended action"] = alerts["cii"].apply(rec_action)

    if st.checkbox("🔴 Live mode (auto-refresh)") and HAS_AUTOREFRESH and len(alerts):
        n = st_autorefresh(interval=2500, key="ops")
        latest = alerts.iloc[n % len(alerts)]
        st.markdown(
            "<div style='background:linear-gradient(135deg,#EF4444,#EC4899);"
            "border-radius:14px;padding:14px 18px;color:#fff;font-weight:600;'>"
            f"🔴 LIVE · {datetime.now().strftime('%H:%M:%S')} · "
            f"{latest['location'].split(',')[0]} · CII {latest['cii']:.0f} · "
            f"{latest['Recommended action']}</div>", unsafe_allow_html=True)
        st.write("")

    m = st.columns(3)
    m[0].metric("Active alerts", len(alerts))
    m[1].metric("Critical (CII ≥ 88)", int((alerts.cii >= 88).sum()))
    m[2].metric("Zones monitored", f"{len(hot):,}")

    st.dataframe(alerts[["cii_rank", "cii", "location", "junction_name", "n_violations",
                         "top_violation", "Recommended action"]].rename(columns={
        "cii_rank": "Rank", "cii": "CII", "location": "Location",
        "junction_name": "Junction", "n_violations": "Violations",
        "top_violation": "Top violation"}),
        use_container_width=True, hide_index=True, height=340)

    # ---- cross-officer dispatch & coordination board (shared across sessions) ----
    st.markdown("#### 🚓 Dispatch & coordination board")
    st.caption("Shared live across every signed-in officer. Tow/crane units are a simulated "
               "fleet; in production these are live GPS units with push-to-mobile alerts.")
    fleet = ops.make_fleet(hot)

    watch = st.checkbox("🔔 Live board (auto-refresh every 5s)", value=True)
    if watch and HAS_AUTOREFRESH:
        st_autorefresh(interval=5000, key="board_refresh")

    e1, e2, e3 = st.columns([2.2, 2.2, 1.1])
    zopts = alerts["location"].tolist() if len(alerts) else hot["location"].head(20).tolist()
    zone = e1.selectbox("Zone", zopts, key="disp_zone")
    act = e2.selectbox("Action", ["Deploy patrol", "Tow & fine", "Install signage / barricade",
                                  "On-spot challan drive", "Escalate to control room"],
                       key="disp_act")
    auto_tow = e3.checkbox("Assign nearest unit", value=True)
    if st.button("📨 Dispatch", type="primary"):
        zrow = hot[hot["location"] == zone]
        unit, dist = (None, None)
        if auto_tow and len(zrow):
            unit, dist = ops.nearest_unit(float(zrow["lat"].iat[0]), float(zrow["lon"].iat[0]), fleet)
        ops.add_dispatch({
            "ts": _time.time(),
            "time": datetime.now().strftime("%H:%M:%S"),
            "officer": st.session_state.get("user", "—"),
            "zone": zone.split(",")[0],
            "cii": float(zrow["cii"].iat[0]) if len(zrow) else None,
            "action": act,
            "unit": unit["unit"] if unit else "—",
            "eta_km": dist if dist is not None else None,
            "status": "Dispatched"})
        msg = f"Dispatched: {act} → {zone.split(',')[0]}"
        if unit:
            msg += f"  ·  nearest unit {unit['unit']} (~{dist} km)"
        st.success(msg)

    board = ops.read_dispatches()
    # toast when a NEW dispatch from another officer appears since we last looked
    max_id = max([b.get("id", 0) for b in board], default=0)
    if max_id > st.session_state.get("board_seen", 0):
        newest = board[0]
        if newest.get("officer") != st.session_state.get("user"):
            st.toast(f"🔔 {newest.get('officer')} → {newest.get('action')} @ "
                     f"{newest.get('zone')}", icon="🚓")
        st.session_state.board_seen = max_id

    open_n = sum(1 for b in board if b.get("status") != "Resolved")
    clears = [b["clear_min"] for b in board if b.get("clear_min") is not None]
    s1, s2, s3 = st.columns(3)
    s1.metric("Open dispatches", open_n)
    s2.metric("Resolved", len(clears))
    s3.metric("Avg time-to-clear", f"{(sum(clears)/len(clears)):.0f} min" if clears else "—")

    if board:
        bdf = pd.DataFrame(board)
        for c in ["time", "officer", "zone", "action", "unit", "status"]:
            if c not in bdf.columns:
                bdf[c] = "—"
        st.dataframe(bdf[["time", "officer", "zone", "action", "unit", "status"]].rename(columns={
            "time": "Time", "officer": "Officer", "zone": "Zone", "action": "Action",
            "unit": "Unit", "status": "Status"}),
            use_container_width=True, hide_index=True, height=240)
        open_ids = [b["id"] for b in board if b.get("status") != "Resolved"]
        rc1, rc2, rc3 = st.columns([2.5, 1, 1])
        if open_ids:
            rid = rc1.selectbox("Resolve a dispatch (logs time-to-clear)", open_ids,
                                format_func=lambda i: f"#{i} · " +
                                next((b.get("zone", "") for b in board if b.get("id") == i), ""),
                                key="resolve_pick")
            if rc2.button("✅ Resolve", key="resolve_btn"):
                ops.resolve_dispatch(rid)
                st.rerun()
        if rc3.button("🗑 Reset board", key="clear_board"):
            ops.clear_dispatches()
            st.session_state.board_seen = 0
            st.rerun()
    else:
        st.info("No dispatches yet — dispatch an action above and it appears instantly "
                "for every officer on the board.")

elif section == "tab_trends":
    tr = load_trends()
    byday = load_byday()
    daily = tr[tr.kind == "daily"].sort_values("order").reset_index(drop=True)
    DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    cursor = None
    live = st.checkbox(t("live_replay", lang), value=False)
    if live and HAS_AUTOREFRESH:
        n = st_autorefresh(interval=1200, key="replay")
        cursor = n % len(daily)
        row = daily.iloc[cursor]
        lc1, lc2 = st.columns(2)
        lc1.metric("Replay day", row["label"])
        lc2.metric("Violations that day", int(row["value"]))
    elif live and not HAS_AUTOREFRESH:
        st.caption("Install `streamlit-autorefresh` to enable live replay.")

    if cursor is not None:
        # cumulative time-lapse for the line + animated bars
        rday = daily.iloc[cursor]["label"]
        dline = daily.iloc[:cursor + 1]
        bh = (byday[(byday.dim == "hour") & (byday.date <= rday)]
              .groupby("key")["value"].sum().reset_index())
        bh.columns = ["label", "value"]
        bh["order"] = bh["label"].astype(int)
        hourly = bh.sort_values("order")
        dd = dline.copy()
        dd["dow"] = pd.to_datetime(dd["label"]).dt.dayofweek
        bw = dd.groupby("dow")["value"].sum().reindex(range(7), fill_value=0)
        dow = pd.DataFrame({"label": DOW, "value": bw.values, "order": range(7)})
        line = line_chart(dline, t("t_daily", lang), mark_last=True)
    else:
        hourly = tr[tr.kind == "hourly"].sort_values("order")
        dow = tr[tr.kind == "dow"].sort_values("order")
        line = line_chart(daily, t("t_daily", lang))

    veh = tr[tr.kind == "vehicle"].sort_values("value", ascending=False)
    vtype = tr[tr.kind == "vtype"].sort_values("value", ascending=False)

    st.plotly_chart(line, use_container_width=True)
    r1 = st.columns(2)
    with r1[0]:
        st.plotly_chart(bar_chart(hourly, t("t_hourly", lang), ramp=True), use_container_width=True)
    with r1[1]:
        st.plotly_chart(bar_chart(dow, t("t_dow", lang)), use_container_width=True)
    r2 = st.columns(2)
    with r2[0]:
        st.plotly_chart(donut(veh["label"], veh["value"], t("t_vehicle", lang)),
                        use_container_width=True)
    with r2[1]:
        st.plotly_chart(donut(vtype["label"], vtype["value"], t("t_vtype", lang)),
                        use_container_width=True)
    g = st.columns([1, 2, 1])
    with g[1]:
        conc = round(hot.head(100)["n_violations"].sum() / meta["n_records"] * 100, 1)
        st.plotly_chart(rainbow_gauge(conc, t("t_gauge", lang)), use_container_width=True)

elif section == "tab_rank":
    topn = st.slider(t("top_n_zones", lang), 5, 50, 20, 5)
    cols = ["cii_rank", "cii", "location", "junction_name", "police_station",
            "n_violations", "active_days", "persistence", "peak_share", "top_violation"]
    tbl = hot[cols].head(topn).copy()
    tbl["persistence"] = (tbl["persistence"] * 100).round(0).astype(int).astype(str) + "%"
    tbl["peak_share"] = (tbl["peak_share"] * 100).round(0).astype(int).astype(str) + "%"
    st.dataframe(tbl.rename(columns={
        "cii_rank": "Rank", "cii": "CII", "location": "Location",
        "junction_name": "Nearest junction", "police_station": "Police station",
        "n_violations": "Violations", "active_days": "Active days",
        "persistence": "Persistence", "peak_share": "Peak share",
        "top_violation": "Top violation"}),
        use_container_width=True, hide_index=True, height=520)
    st.download_button(t("dl_priorities", lang), hot[cols].head(topn).to_csv(index=False),
                       "enforcement_priorities.csv", mime="text/csv")

elif section == "tab_off":
    s = meta.get("offender_summary", {})
    o1, o2, o3 = st.columns(3)
    o1.metric(t("repeat_offenders", lang), f"{s.get('repeat_offenders', 0):,}")
    o2.metric(t("share_violations", lang), f"{s.get('repeat_share_pct', 0)}%")
    o3.metric(t("worst_vehicle", lang), f"{s.get('worst_count', 0)}")

    st.markdown("##### Offender intelligence")
    cc = st.columns(2)
    with cc[0]:
        topo = off.head(12)
        st.plotly_chart(bar_chart(
            pd.DataFrame({"label": topo["vehicle_number"], "value": topo["n_violations"]}),
            "Top 12 offenders · violations", ramp=True), use_container_width=True)
    with cc[1]:
        vt = off.groupby("vehicle_type").size().sort_values(ascending=False)
        st.plotly_chart(donut(vt.index.tolist(), vt.values.tolist(),
                              "Offenders by vehicle type"), use_container_width=True)
    zh = off.groupby("n_zones").size().reset_index(name="cnt").sort_values("n_zones")
    st.plotly_chart(bar_chart(
        pd.DataFrame({"label": zh["n_zones"].astype(str) + " zone(s)", "value": zh["cnt"]}),
        "Spatial spread · how many distinct zones each offender hits"),
        use_container_width=True)

    # ---- escalation ladder (chronic-offender enforcement tiers) ----
    st.markdown("##### ⚖️ Repeat-offender escalation ladder")
    st.caption("Chronic plates are auto-tiered for escalating action — in production these "
               "fire as e-challan notices / RTO referrals, directly targeting the 34%.")
    tiers_all = off["n_violations"].apply(ops.escalation_tier)
    off_e = off.copy()
    off_e["tier"] = [x[0] for x in tiers_all]
    off_e["tier_icon"] = [x[1] for x in tiers_all]
    off_e["rec_action"] = [x[2] for x in tiers_all]
    tc = off_e.groupby("tier_icon").size()
    tcols = st.columns(4)
    for col, (ic, nm) in zip(tcols, [("🔴", "Chronic"), ("🟠", "Habitual"),
                                     ("🟡", "Repeat"), ("🔵", "Watchlist")]):
        col.metric(f"{ic} {nm}", int(tc.get(ic, 0)))

    q = st.text_input(t("search_vehicle", lang), key="off_search")
    view = off_e
    if q:
        view = off_e[off_e["vehicle_number"].str.contains(q, case=False, na=False)
                     | off_e["top_location"].str.contains(q, case=False, na=False)]
    n_off = st.slider(t("top_n_off", lang), 5, 100, 25, 5, key="off_n")
    view = view.copy()
    view["Tier"] = view["tier_icon"] + " " + view["tier"]
    st.dataframe(view.head(n_off)[["rank", "vehicle_number", "n_violations", "n_zones",
                                   "vehicle_type", "Tier", "rec_action", "last_seen"]].rename(
        columns={"rank": "Rank", "vehicle_number": "Vehicle (anon.)",
                 "n_violations": "Violations", "n_zones": "Zones hit", "vehicle_type": "Type",
                 "rec_action": "Recommended action", "last_seen": "Last seen"}),
        use_container_width=True, hide_index=True, height=420)
    st.download_button(t("dl_offenders", lang),
                       view.head(n_off).drop(columns=["tier_icon"]).to_csv(index=False),
                       "repeat_offenders.csv", mime="text/csv", key="off_dl")

    with st.expander("📄 Generate a formal notice (e-challan draft)"):
        pick = st.selectbox("Vehicle", view.head(n_off)["vehicle_number"].tolist(),
                            key="notice_v")
        r = off_e[off_e["vehicle_number"] == pick].iloc[0]
        notice = (f"BENGALURU TRAFFIC POLICE — REPEAT-OFFENDER NOTICE\n"
                  f"-----------------------------------------------\n"
                  f"Vehicle (anonymised): {pick}\n"
                  f"Vehicle type        : {r['vehicle_type']}\n"
                  f"Recorded violations : {r['n_violations']} across {r['n_zones']} zone(s)\n"
                  f"Period              : {r['first_seen']} to {r['last_seen']}\n"
                  f"Most-seen location  : {r['top_location']}\n"
                  f"Escalation tier     : {r['tier_icon']} {r['tier']}\n"
                  f"Recommended action  : {r['rec_action']}\n\n"
                  f"As per repeat-violation provisions, the above vehicle is liable for "
                  f"escalated penalty. This is a system-generated draft for review.\n")
        st.code(notice)
        st.download_button("⬇️ Download notice (TXT)", notice, f"notice_{pick}.txt",
                           mime="text/plain", key="notice_dl")

elif section == "tab_fc":
    day = fc["forecast_for"].iat[0]
    st.caption(f"{day}")
    topf = fc.head(25).copy()
    fc_layer = pdk.Layer("ScatterplotLayer", topf, pickable=True, get_position="[lon, lat]",
                         get_radius="pred_intensity * 6 + 60",
                         get_fill_color="[244, 114, 182, 160]")
    st.pydeck_chart(pdk.Deck(
        layers=[fc_layer],
        initial_view_state=pdk.ViewState(latitude=12.97, longitude=77.59, zoom=11, pitch=0),
        map_style=MAP_STYLE,
        tooltip={"html": "Risk #{risk_rank} · {pred_intensity}<br/>{location}"},
    ), use_container_width=True, height=520, key=f"fcmap_{THEME}")
    st.dataframe(topf[["risk_rank", "location", "junction_name",
                       "pred_intensity", "cii"]].rename(columns={
        "risk_rank": "Risk rank", "location": "Location", "junction_name": "Nearest junction",
        "pred_intensity": "Predicted intensity", "cii": "Current CII"}),
        use_container_width=True, hide_index=True)

elif section == "tab_patrol":
    st.subheader("🗓️ Patrol-beat & shift planner")
    day = fc["forecast_for"].iat[0]
    st.caption(f"Tomorrow's predicted hotspots ({day}) grouped by station jurisdiction — "
               "a deployable morning briefing. Zones from the LightGBM forecast; suggested "
               "shift windows from each zone's peak-hour profile.")

    plan = ops.patrol_plan(fc, hot, top_zones=60)
    if not len(plan):
        st.info("No forecast zones available to plan.")
    else:
        summ = (plan.groupby("police_station")
                .agg(zones=("h3", "count"), intensity=("pred_intensity", "sum"),
                     units=("units", "sum"))
                .sort_values("intensity", ascending=False).reset_index())
        c = st.columns(3)
        c[0].metric("Hotspot zones tomorrow", len(plan))
        c[1].metric("Stations to brief", plan["police_station"].nunique())
        c[2].metric("Patrol units to deploy", int(plan["units"].sum()))

        st.markdown("##### 🚦 Priority stations tomorrow")
        st.plotly_chart(bar_chart(
            pd.DataFrame({"label": summ["police_station"].head(10),
                          "value": summ["intensity"].head(10).round(0)}),
            "Top 10 stations by total predicted intensity", ramp=True),
            use_container_width=True)

        stations = ["All divisions"] + summ["police_station"].tolist()
        pick = st.selectbox("Division / station beat", stations, key="patrol_div")
        view = plan if pick == "All divisions" else plan[plan["police_station"] == pick]

        mlayer = pdk.Layer("ScatterplotLayer", view, pickable=True, get_position="[lon, lat]",
                           get_radius="pred_intensity * 6 + 80",
                           get_fill_color="[124, 58, 237, 170]")
        st.pydeck_chart(pdk.Deck(
            layers=[mlayer],
            initial_view_state=pdk.ViewState(latitude=12.97, longitude=77.59, zoom=11, pitch=0),
            map_style=MAP_STYLE,
            tooltip={"html": "<b>{location}</b><br/>pred {pred_intensity} · "
                             "{units} unit(s)<br/>{shift}"}),
            use_container_width=True, height=420, key=f"patrolmap_{THEME}")

        brief = view.copy()
        brief["order"] = range(1, len(brief) + 1)
        show = brief[["order", "police_station", "location", "junction_name",
                      "pred_intensity", "shift", "units"]].rename(columns={
            "order": "#", "police_station": "Station", "location": "Zone",
            "junction_name": "Junction", "pred_intensity": "Predicted intensity",
            "shift": "Suggested shift", "units": "Units"})
        st.dataframe(show, use_container_width=True, hide_index=True, height=380)
        st.download_button("⬇️  Download tomorrow's patrol briefing (CSV)",
                           show.to_csv(index=False), "patrol_briefing.csv",
                           mime="text/csv", key="patrol_dl")

elif section == "tab_whatif":
    st.subheader("🧪 What-if intervention simulator")
    st.caption("Project the CII drop from an intervention using the *same* published CII "
               "weights (volume 45% · persistence 30% · peak 25%). Lever effects are "
               "transparent, configurable assumptions — not a black box.")

    wcol = st.columns([2.4, 2])
    zopts = hot.sort_values("cii", ascending=False)["location"].head(150).tolist()
    zsel = wcol[0].selectbox("Target zone", zopts, key="wi_zone")
    levers = wcol[1].multiselect("Intervention(s)", list(ops.INTERVENTIONS.keys()),
                                 default=["Bollards / barricade"], key="wi_lev")

    zrow = hot[hot["location"] == zsel].iloc[0]
    cur_cii = float(zrow["cii"])
    reductions = ops.combine_interventions(levers)
    new_cii, eff_pct = ops.whatif_new_cii(cur_cii, reductions, meta.get("cii_weights", {}))
    cur_rank = int(zrow["cii_rank"])
    proj_rank = ops.new_rank(new_cii, hot["cii"].tolist())

    k = st.columns(3)
    with k[0]:
        kpi_card("🎯", "Projected CII", f"{new_cii:.0f}", accent="#22D3EE",
                 sub=f"<span style='color:#34D399;'>↓ from {cur_cii:.0f} (−{eff_pct:.0f}%)</span>")
    with k[1]:
        kpi_card("📊", "Projected city rank", f"#{proj_rank}", accent=VIOLET,
                 sub=f"<span style='color:#34D399;'>from #{cur_rank} "
                 f"(↓ {max(0, proj_rank - cur_rank)} places)</span>")
    with k[2]:
        kpi_card("🧩", "Levers applied", f"{len(levers)}", accent="#FACC15",
                 sub="combined with diminishing returns")

    st.write("")
    st.plotly_chart(bar_chart(
        pd.DataFrame({"label": ["Current CII", "Projected CII"], "value": [cur_cii, new_cii]}),
        f"{zsel.split(',')[0]} — projected impact of intervention", ramp=False),
        use_container_width=True)

    comp = pd.DataFrame({
        "Component": ["Severity-weighted volume", "Persistence", "Peak concentration"],
        "Weight": ["45%", "30%", "25%"],
        "Modelled reduction": [f"−{reductions['volume'] * 100:.0f}%",
                               f"−{reductions['persistence'] * 100:.0f}%",
                               f"−{reductions['peak'] * 100:.0f}%"]})
    st.markdown("##### How the projection is built")
    st.dataframe(comp, use_container_width=True, hide_index=True)
    st.caption("Each lever reduces components by configurable fractions; multiple levers "
               "combine multiplicatively. The headline change is the weight-blended "
               "reduction applied to this zone's CII — fully auditable.")

elif section == "tab_event":
    st.subheader("🎪 Event mode — venue surge projection")
    st.caption("Project congestion around a known venue on event days (match / concert / "
               "sale). Surge = each nearby zone's CII × an event multiplier, from its "
               "historical pattern — useful for pre-positioning before the rush.")

    VENUES = {
        "M. Chinnaswamy Stadium (cricket)": (12.9788, 77.5996),
        "Sree Kanteerava Stadium": (12.9617, 77.5972),
        "Orion Mall, Rajajinagar": (13.0108, 77.5550),
        "Phoenix Marketcity, Whitefield": (12.9959, 77.6965),
        "Mantri Square, Malleshwaram": (13.0068, 77.5705),
        "Kempegowda Bus Station (Majestic)": (12.9774, 77.5717),
        "MG Road / Brigade Road": (12.9756, 77.6068),
    }
    EVENTS = {"Cricket match / concert (high)": 1.6, "Mall sale / festival (medium)": 1.4,
              "Weekday office rush (low)": 1.25}

    ec = st.columns([2.3, 2, 1])
    venue = ec[0].selectbox("Venue", list(VENUES.keys()), key="ev_venue")
    etype = ec[1].selectbox("Event type", list(EVENTS.keys()), key="ev_type")
    kr = ec[2].slider("Radius (rings)", 1, 3, 2, key="ev_k")

    vlat, vlon = VENUES[venue]
    mult = EVENTS[etype]
    tmp = hot[["h3", "lat", "lon"]].copy()
    tmp["_d"] = (tmp["lat"] - vlat) ** 2 + (tmp["lon"] - vlon) ** 2
    center_h3 = tmp.nsmallest(1, "_d")["h3"].iat[0]
    surge = ops.event_surge(hot, center_h3, kr, mult)

    if not len(surge):
        st.info("No mapped hotspot zones near this venue in the dataset.")
    else:
        m = st.columns(3)
        m[0].metric("Zones in surge radius", len(surge))
        m[1].metric("Peak projected CII", f"{surge['surge_cii'].max():.0f}")
        m[2].metric("Avg added load", f"+{surge['delta'].mean():.0f} CII")

        surge2 = surge.copy()
        surge2["radius"] = surge2["surge_cii"] * 5 + 60
        slayer = pdk.Layer("ScatterplotLayer", surge2, pickable=True, get_position="[lon, lat]",
                           get_radius="radius", get_fill_color="[239, 68, 68, 160]")
        vlayer = pdk.Layer("ScatterplotLayer", pd.DataFrame([{"lat": vlat, "lon": vlon}]),
                           get_position="[lon, lat]", get_radius=180,
                           get_fill_color="[124, 58, 237, 230]")
        st.pydeck_chart(pdk.Deck(
            layers=[slayer, vlayer],
            initial_view_state=pdk.ViewState(latitude=vlat, longitude=vlon, zoom=13, pitch=0),
            map_style=MAP_STYLE,
            tooltip={"html": "<b>{location}</b><br/>CII {cii} → surge {surge_cii} (+{delta})"}),
            use_container_width=True, height=440, key=f"eventmap_{THEME}")

        show = surge[["location", "junction_name", "cii", "surge_cii", "delta",
                      "n_violations"]].rename(columns={
            "location": "Zone", "junction_name": "Junction", "cii": "Normal CII",
            "surge_cii": "Event CII", "delta": "Δ surge", "n_violations": "Hist. violations"})
        st.dataframe(show, use_container_width=True, hide_index=True, height=320)
        st.caption(f"Projection: normal CII × {mult} (event multiplier), capped at 100. "
                   "The violet dot is the venue; red dots are expected surge zones.")

st.divider()
st.caption(f"CII = severity-weighted volume (45%) + persistence (30%) + peak "
           f"concentration (25%), amplified near junctions. Forecast: LightGBM, "
           f"MAE {mm['valid_mae']} ({mm['improvement_pct']}% better than baseline).")
