"""Light i18n layer.

Two jobs:
  1. UI string translations for English / Kannada / Hindi.
  2. Resolve a native-script (Kannada/Hindi) place query to the English place
     names in the data, via transliteration + fuzzy matching.

NOTE: the Kannada/Hindi UI strings are standard civic terms but should be
sanity-checked by a native speaker before the finale.
"""
import re
import difflib
import unicodedata

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

# label -> code, and code -> Web Speech API locale
LANGS = {"English": "en", "ಕನ್ನಡ": "kn", "हिन्दी": "hi"}
SPEECH_LANG = {"en": "en-IN", "kn": "kn-IN", "hi": "hi-IN"}

STRINGS = {
    "title": {
        "en": "ParkSight — Parking-Induced Congestion Intelligence",
        "kn": "ಪಾರ್ಕ್‌ಸೈಟ್ — ಪಾರ್ಕಿಂಗ್ ದಟ್ಟಣೆ ವಿಶ್ಲೇಷಣೆ",
        "hi": "पार्कसाइट — पार्किंग जनित भीड़ विश्लेषण"},
    "kpi_violations": {"en": "Parking violations", "kn": "ಪಾರ್ಕಿಂಗ್ ಉಲ್ಲಂಘನೆಗಳು",
                       "hi": "पार्किंग उल्लंघन"},
    "kpi_zones": {"en": "Impact zones", "kn": "ಪ್ರಭಾವ ವಲಯಗಳು", "hi": "प्रभाव क्षेत्र"},
    "kpi_high": {"en": "High-impact (CII ≥ 70)", "kn": "ಹೆಚ್ಚು-ಪ್ರಭಾವ (CII ≥ 70)",
                 "hi": "उच्च-प्रभाव (CII ≥ 70)"},
    "kpi_mae": {"en": "Forecast MAE", "kn": "ಮುನ್ಸೂಚನೆ MAE", "hi": "पूर्वानुमान MAE"},
    "voice_nav": {"en": "Voice / command navigation", "kn": "ಧ್ವನಿ / ಆದೇಶ ಸಂಚಲನೆ",
                  "hi": "वॉइस / कमांड नेविगेशन"},
    "ask": {"en": "Ask in plain language", "kn": "ಕನ್ನಡದಲ್ಲಿ ಹುಡುಕಿ", "hi": "हिंदी में खोजें"},
    "placeholder": {"en": "e.g. 'show worst zones in Shivaji Nagar'  ·  'read top 5'",
                    "kn": "ಉದಾ: 'ಶಿವಾಜಿನಗರದ ಕೆಟ್ಟ ವಲಯಗಳು'",
                    "hi": "उदा: 'शिवाजी नगर के सबसे खराब क्षेत्र'"},
    "speak": {"en": "🎤 Speak", "kn": "🎤 ಮಾತನಾಡಿ", "hi": "🎤 बोलें"},
    "stop": {"en": "⏹ Stop", "kn": "⏹ ನಿಲ್ಲಿಸಿ", "hi": "⏹ रोकें"},
    "understood": {"en": "Understood", "kn": "ಅರ್ಥವಾಯಿತು", "hi": "समझ गया"},
    "tab_map": {"en": "🗺️  Impact map", "kn": "🗺️  ಪ್ರಭಾವ ನಕ್ಷೆ", "hi": "🗺️  प्रभाव नक्शा"},
    "tab_ops": {"en": "🚨  Live alerts", "kn": "🚨  ಲೈವ್ ಎಚ್ಚರಿಕೆ", "hi": "🚨  लाइव अलर्ट"},
    "tab_rank": {"en": "📋  Enforcement priorities", "kn": "📋  ಜಾರಿ ಆದ್ಯತೆಗಳು",
                 "hi": "📋  प्रवर्तन प्राथमिकताएँ"},
    "tab_off": {"en": "🚨  Repeat offenders", "kn": "🚨  ಪುನರಾವರ್ತಿತ ಅಪರಾಧಿಗಳು",
                "hi": "🚨  बार-बार उल्लंघनकर्ता"},
    "tab_fc": {"en": "🔮  Tomorrow's forecast", "kn": "🔮  ನಾಳಿನ ಮುನ್ಸೂಚನೆ",
               "hi": "🔮  कल का पूर्वानुमान"},
    "tab_patrol": {"en": "🗓️  Patrol planner", "kn": "🗓️  ಗಸ್ತು ಯೋಜನೆ",
                   "hi": "🗓️  गश्त योजना"},
    "tab_whatif": {"en": "🧪  What-if simulator", "kn": "🧪  ವಾಟ್-ಇಫ್ ಸಿಮ್ಯುಲೇಟರ್",
                   "hi": "🧪  व्हाट-इफ सिम्युलेटर"},
    "tab_event": {"en": "🎪  Event mode", "kn": "🎪  ಈವೆಂಟ್ ಮೋಡ್",
                  "hi": "🎪  इवेंट मोड"},
    "min_cii": {"en": "Minimum CII to display", "kn": "ಪ್ರದರ್ಶಿಸಲು ಕನಿಷ್ಠ CII",
                "hi": "दिखाने हेतु न्यूनतम CII"},
    "top_n_zones": {"en": "Show top N zones", "kn": "ಮೇಲಿನ N ವಲಯಗಳನ್ನು ತೋರಿಸಿ",
                    "hi": "शीर्ष N क्षेत्र दिखाएँ"},
    "dl_priorities": {"en": "⬇️  Download enforcement priorities (CSV)",
                      "kn": "⬇️  ಜಾರಿ ಆದ್ಯತೆಗಳನ್ನು ಡೌನ್‌ಲೋಡ್ ಮಾಡಿ (CSV)",
                      "hi": "⬇️  प्रवर्तन प्राथमिकताएँ डाउनलोड करें (CSV)"},
    "repeat_offenders": {"en": "Repeat offenders", "kn": "ಪುನರಾವರ್ತಿತ ಅಪರಾಧಿಗಳು",
                         "hi": "बार-बार उल्लंघनकर्ता"},
    "share_violations": {"en": "Share of all violations", "kn": "ಎಲ್ಲಾ ಉಲ್ಲಂಘನೆಗಳ ಪಾಲು",
                         "hi": "कुल उल्लंघनों में हिस्सा"},
    "worst_vehicle": {"en": "Worst single vehicle", "kn": "ಅತಿ ಕೆಟ್ಟ ಏಕೈಕ ವಾಹನ",
                      "hi": "सबसे खराब एकल वाहन"},
    "search_vehicle": {"en": "Search a vehicle ID or area",
                       "kn": "ವಾಹನ ID ಅಥವಾ ಪ್ರದೇಶ ಹುಡುಕಿ", "hi": "वाहन ID या क्षेत्र खोजें"},
    "top_n_off": {"en": "Show top N offenders", "kn": "ಮೇಲಿನ N ಅಪರಾಧಿಗಳನ್ನು ತೋರಿಸಿ",
                  "hi": "शीर्ष N उल्लंघनकर्ता दिखाएँ"},
    "dl_offenders": {"en": "⬇️  Download offender watchlist (CSV)",
                     "kn": "⬇️  ಅಪರಾಧಿಗಳ ಪಟ್ಟಿ ಡೌನ್‌ಲೋಡ್ ಮಾಡಿ (CSV)",
                     "hi": "⬇️  उल्लंघनकर्ता सूची डाउनलोड करें (CSV)"},
    "language": {"en": "Language", "kn": "ಭಾಷೆ", "hi": "भाषा"},
    "theme": {"en": "Theme", "kn": "ಥೀಮ್", "hi": "थीम"},
    "dark": {"en": "🌙 Dark", "kn": "🌙 ಕಪ್ಪು", "hi": "🌙 डार्क"},
    "light": {"en": "☀️ Light", "kn": "☀️ ಬೆಳಕು", "hi": "☀️ लाइट"},
    "history": {"en": "🕘 Your searches this session", "kn": "🕘 ಈ ಅವಧಿಯ ಹುಡುಕಾಟಗಳು",
                "hi": "🕘 इस सत्र की खोजें"},
    "clear_history": {"en": "Clear history", "kn": "ಇತಿಹಾಸ ಅಳಿಸಿ", "hi": "इतिहास साफ़ करें"},
    "no_history": {"en": "No searches yet.", "kn": "ಇನ್ನೂ ಹುಡುಕಾಟಗಳಿಲ್ಲ.",
                   "hi": "अभी तक कोई खोज नहीं।"},
    "tab_trends": {"en": "📈  Trends", "kn": "📈  ಪ್ರವೃತ್ತಿಗಳು", "hi": "📈  रुझान"},
    "t_daily": {"en": "Daily violations", "kn": "ದೈನಂದಿನ ಉಲ್ಲಂಘನೆಗಳು", "hi": "दैनिक उल्लंघन"},
    "t_hourly": {"en": "By hour of day", "kn": "ಗಂಟೆಯ ಪ್ರಕಾರ", "hi": "घंटे के अनुसार"},
    "t_vehicle": {"en": "By vehicle type", "kn": "ವಾಹನ ಪ್ರಕಾರ", "hi": "वाहन प्रकार के अनुसार"},
    "t_vtype": {"en": "By violation type", "kn": "ಉಲ್ಲಂಘನೆ ಪ್ರಕಾರ", "hi": "उल्लंघन प्रकार के अनुसार"},
    "t_dow": {"en": "By day of week", "kn": "ವಾರದ ದಿನದ ಪ್ರಕಾರ", "hi": "सप्ताह के दिन अनुसार"},
    "t_gauge": {"en": "Top-100 zones · share of all violations",
                "kn": "ಮೇಲಿನ 100 ವಲಯಗಳ ಪಾಲು", "hi": "शीर्ष 100 क्षेत्रों का हिस्सा"},
    "live_replay": {"en": "▶ Live replay (simulated from historical data)",
                    "kn": "▶ ಲೈವ್ ರಿಪ್ಲೇ (ಐತಿಹಾಸಿಕ ದತ್ತಾಂಶದಿಂದ)",
                    "hi": "▶ लाइव रीप्ले (ऐतिहासिक डेटा से)"},
}


def t(key, lang):
    """Translate a UI string key into the chosen language (falls back to English)."""
    return STRINGS.get(key, {}).get(lang) or STRINGS.get(key, {}).get("en", key)


def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z]", "", s.lower())
    s = re.sub(r"([a-z])\1+", r"\1", s)          # collapse doubled letters
    return s.replace("nagara", "nagar")


def romanize(text, lang):
    scr = {"kn": sanscript.KANNADA, "hi": sanscript.DEVANAGARI}.get(lang)
    if scr is None:
        return text
    try:
        return transliterate(text, scr, sanscript.IAST)
    except Exception:
        return text


def build_area_vocab(hot):
    """Distinct locality names from the hotspot location strings."""
    areas = set()
    for loc in hot["location"].dropna():
        for p in [x.strip() for x in str(loc).split(",")][1:4]:
            pl = p.lower()
            if p and "bengaluru" not in pl and "karnataka" not in pl and "pin" not in pl:
                areas.add(p)
    return sorted(areas)


def resolve_area(query, lang, area_vocab):
    """Map a (possibly Kannada/Hindi) place query to an English locality name."""
    has_native = any(ord(c) > 127 for c in query)
    rom = romanize(query, lang) if (has_native or lang != "en") else query
    key = _norm(rom)
    if not key:
        return None
    norm_map = {_norm(a): a for a in area_vocab}
    best = difflib.get_close_matches(key, list(norm_map.keys()), n=1, cutoff=0.55)
    return norm_map[best[0]] if best else None
