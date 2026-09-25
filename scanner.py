print("===== NSE SCANNER VERSION 2026-09-23-V3 =====")
print("===== IST + TELEGRAM HTML + TRADINGVIEW LINK =====")

import os
import json
import html
import requests
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd
from tvscreener import StockScreener, StockField, Market


# =========================================================
# CONFIGURATION
# =========================================================

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

SENT_FILE = "sent_alerts.json"
COOLDOWN_MINUTES = 30

IST = timezone(timedelta(hours=5, minutes=30))

# Global log buffer
LOG_BUFFER = []


# =========================================================
# LOG FUNCTION (Console + Buffer)
# =========================================================

def log(msg=""):
    """Print to console AND store in LOG_BUFFER for Telegram."""
    text = str(msg)
    print(text)
    LOG_BUFFER.append(text)


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram configuration missing")
        print(msg)
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(url, data=payload, timeout=15)

        print("Telegram HTTP Status:", response.status_code)
        print("Telegram Response:", response.text)

        if response.status_code == 200:
            result = response.json()
            if result.get("ok") is True:
                print("Telegram message sent successfully")
                return True

        print("Telegram message failed")
        return False

    except Exception as e:
        print("Telegram error:", e)
        return False


def send_telegram_long(msg):
    """Telegram message limit (4096) ko respect karte hue bhejo.
    Agar lamba hai to chunks me todkar bhejo."""
    MAX_LEN = 4000

    if len(msg) <= MAX_LEN:
        return send_telegram(msg)

    # Chunks me todo
    parts = []
    while len(msg) > MAX_LEN:
        split_at = msg.rfind("\n", 0, MAX_LEN)
        if split_at == -1:
            split_at = MAX_LEN
        parts.append(msg[:split_at])
        msg = msg[split_at:].lstrip("\n")

    parts.append(msg)

    success = True
    for i, part in enumerate(parts):
        header = f"<b>📋 Part {i+1}/{len(parts)}</b>\n"
        if not send_telegram(header + part):
            success = False

    return success


# =========================================================
# LOAD / SAVE SENT ALERTS
# =========================================================

def load_sent():
    if not os.path.exists(SENT_FILE):
        return {}

    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log("Error reading sent file: " + str(e))
        return {}


def save_sent(data):
    try:
        with open(SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log("Error saving sent file: " + str(e))
        return False


# =========================================================
# SIGNAL
# =========================================================

def get_signal(val):
    if pd.isna(val):
        return "NEUTRAL"
    try:
        val = float(val)
    except Exception:
        return "NEUTRAL"

    if val >= 0.5:
        return "STRONG BUY"
    if val >= 0.1:
        return "BUY"
    if val <= -0.5:
        return "STRONG SELL"
    if val <= -0.1:
        return "SELL"
    return "NEUTRAL"


# =========================================================
# CLEAN SYMBOL
# =========================================================

def clean_symbol(symbol):
    if pd.isna(symbol):
        return ""
    symbol = str(symbol).strip().upper()
    if ":" in symbol:
        symbol = symbol.split(":")[-1]
    return symbol


# =========================================================
# TRADINGVIEW LINK
# =========================================================

def tradingview_link(symbol):
    symbol = clean_symbol(symbol)
    encoded_symbol = quote(f"NSE:{symbol}", safe="")
    return f"https://www.tradingview.com/chart/?symbol={encoded_symbol}"


# =========================================================
# START
# =========================================================

now = datetime.now(IST)

log()
log("=" * 65)
log("NSE SCANNER V3")
log("UTC TIME : " + datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M:%S"))
log("IST TIME : " + now.strftime("%d-%b-%Y %H:%M:%S"))
log("=" * 65)


# =========================================================
# FIRST SCAN
# =========================================================

try:
    ss = StockScreener()
    ss.set_markets(Market.INDIA)
    ss.select(
        StockField.NAME,
        StockField.PRICE,
        StockField.HULLMA20,
        StockField.SIMPLE_MOVING_AVERAGE_50,
        StockField.RECOMMEND_ALL_15
    )
    ss.where(StockField.HULLMA20 > StockField.SIMPLE_MOVING_AVERAGE_50)
    ss.set_range(0, 500)
    df = ss.get()

except Exception as e:
    log("First scanner error: " + str(e))
    raise


if df.empty:
    log("No stocks found")
    send_telegram("❌ <b>NSE Scanner:</b> कोई स्टॉक नहीं मिला")
    raise SystemExit


# =========================================================
# SYMBOL CLEANING
# =========================================================

df["Symbol"] = df["Symbol"].apply(clean_symbol)
df = df[df["Symbol"] != ""]
df = df.drop_duplicates(subset=["Symbol"], keep="first")


# =========================================================
# FIND 15 MIN RECOMMENDATION COLUMN
# =========================================================

rating_col = next(
    (c for c in df.columns if "Recommend" in c and "15" in c),
    None
)

if rating_col is None:
    log("15 minute recommendation column not found.")
    log(str(df.columns.tolist()))
    send_telegram("⚠️ <b>NSE Scanner:</b> Rating column नहीं मिला")
    raise SystemExit

log("Rating column: " + rating_col)


# =========================================================
# SIGNAL
# =========================================================

df["Signal"] = df[rating_col].apply(get_signal)

strong_df = df[df[rating_col].abs() >= 0.5].copy()
strong_symbols = strong_df["Symbol"].tolist()

log("Strong Buy/Sell: " + str(len(strong_df)))


# =========================================================
# INTRADAY SCAN
# =========================================================

intraday_df = pd.DataFrame()

if strong_symbols:
    try:
        ss2 = StockScreener()
        ss2.set_markets(Market.INDIA)
        ss2.select(
            StockField.NAME,
            StockField.PRICE,
            StockField.CHANGE_PERCENT,
            StockField.VOLUME,
            StockField.RELATIVE_VOLUME,
            StockField.RELATIVE_STRENGTH_INDEX_14,
            StockField.HULLMA20,
            StockField.SIMPLE_MOVING_AVERAGE_50,
            StockField.RECOMMEND_ALL_15
        )
        ss2.where(StockField.HULLMA20 > StockField.SIMPLE_MOVING_AVERAGE_50)
        ss2.where(StockField.RELATIVE_STRENGTH_INDEX_14 > 40)
        ss2.where(StockField.RELATIVE_STRENGTH_INDEX_14 < 70)
        ss2.where(StockField.RELATIVE_VOLUME > 1)
        ss2.set_range(0, 500)

        temp = ss2.get()

        if not temp.empty:
            temp["Symbol"] = temp["Symbol"].apply(clean_symbol)
            temp = temp[temp["Symbol"] != ""]
            temp = temp.drop_duplicates(subset=["Symbol"], keep="first")

            intraday_df = temp[temp["Symbol"].isin(strong_symbols)].copy()

            intraday_rating_col = next(
                (c for c in intraday_df.columns if "Recommend" in c and "15" in c),
                None
            )

            if intraday_rating_col:
                intraday_df["Signal"] = intraday_df[intraday_rating_col].apply(get_signal)

    except Exception as e:
        log("Intraday scanner error: " + str(e))
        raise


log("Intraday qualified: " + str(len(intraday_df)))


# =========================================================
# COOLDOWN
# =========================================================

sent = load_sent()
now = datetime.now(IST)
new_alerts = []

for _, row in intraday_df.iterrows():
    symbol = clean_symbol(row["Symbol"])
    if not symbol:
        continue

    last_sent = sent.get(symbol)

    if last_sent:
        try:
            last_time = datetime.fromisoformat(last_sent)

            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=IST)

            if now - last_time < timedelta(minutes=COOLDOWN_MINUTES):
                log(symbol + " skipped - cooldown")
                continue

        except Exception as e:
            log("Cooldown parse error: " + symbol + " " + str(e))

    new_alerts.append(row)


# =========================================================
# BUILD TELEGRAM MESSAGE (SUMMARY + STOCKS)
# =========================================================

if not new_alerts:
    log("No new alerts")
    log("Current IST: " + now.strftime("%d-%b-%Y %H:%M:%S"))

    summary_msg = (
        f"📊 <b>NSE SCAN</b> "
        f"({now.strftime('%d-%b %I:%M %p')} IST)\n\n"
        f"🔥 Strong Buy/Sell: <b>{len(strong_df)}</b>\n"
        f"🎯 Intraday योग्य: <b>{len(intraday_df)}</b>\n\n"
        f"✅ <b>कोई नया अलर्ट नहीं</b>\n"
        f"(सभी stocks पिछले {COOLDOWN_MINUTES} मिनट में भेजे जा चुके हैं)"
    )

    send_telegram(summary_msg)
    raise SystemExit


# अगर नए alerts हैं — summary + stocks
msg = (
    f"📊 <b>NSE SCAN</b> "
    f"({now.strftime('%d-%b %I:%M %p')} IST)\n\n"
)

msg += f"🔥 Strong Buy/Sell: <b>{len(strong_df)}</b>\n"
msg += f"🎯 Intraday योग्य: <b>{len(intraday_df)}</b>\n\n"
msg += f"🆕 <b>नए अलर्ट ({len(new_alerts)}):</b>\n"


# =========================================================
# ADD STOCKS
# =========================================================

for row in new_alerts:
    symbol = clean_symbol(row["Symbol"])
    signal = str(row.get("Signal", "N/A"))

    rsi = row.get("Relative Strength Index (14)", "N/A")
    if pd.notna(rsi):
        try:
            rsi = f"{float(rsi):.1f}"
        except Exception:
            rsi = str(rsi)
    else:
        rsi = "N/A"

    rvol = row.get("Relative Volume", "N/A")
    if pd.notna(rvol):
        try:
            rvol = f"{float(rvol):.2f}"
        except Exception:
            rvol = str(rvol)
    else:
        rvol = "N/A"

    tv_url = tradingview_link(symbol)
    safe_symbol = html.escape(symbol)
    safe_signal = html.escape(signal)

    msg += (
        f'• <a href="{tv_url}">'
        f'<b>{safe_symbol}</b>'
        f'</a>'
        f' — {safe_signal}'
        f' | RSI: {rsi}'
        f' | RVOL: {rvol}\n'
    )


# =========================================================
# DEBUG MESSAGE
# =========================================================

log()
log("Telegram message preview:")
log(msg)
log()


# =========================================================
# SEND SUMMARY
# =========================================================

telegram_success = send_telegram(msg)


# =========================================================
# SAVE COOLDOWN AFTER SUCCESS
# =========================================================

if telegram_success:
    for row in new_alerts:
        symbol = clean_symbol(row["Symbol"])
        sent[symbol] = now.isoformat()

    save_sent(sent)
    log(f"{len(new_alerts)} alerts sent successfully")
else:
    log("Telegram send failed")
    log("sent_alerts.json was not updated")


# =========================================================
# FINISH
# =========================================================

log()
log("=" * 65)
log("Finished IST: " + now.strftime("%d-%b-%Y %H:%M:%S"))
log("Strong: " + str(len(strong_df)))
log("Intraday: " + str(len(intraday_df)))
log("New alerts: " + str(len(new_alerts)))
log("=" * 65)


# =========================================================
# SEND FULL LOG TO TELEGRAM (as <pre> block, chunked)
# =========================================================

full_log = "\n".join(LOG_BUFFER)

# Escape HTML
safe_log = html.escape(full_log)

# Send as monospace block — chunked if too long
send_telegram_long(
    f"<b>📋 NSE Scanner V3 — Full Log</b>\n"
    f"<pre>{safe_log}</pre>"
)
