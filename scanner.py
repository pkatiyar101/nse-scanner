print("===== NSE SCANNER VERSION 2026-09-25-V5 =====")
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
COOLDOWN_MINUTES = 60

# India Standard Time
IST = timezone(timedelta(hours=5, minutes=30))


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
        response = requests.post(
            url,
            data=payload,
            timeout=15
        )

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


# =========================================================
# LOAD SENT ALERTS
# =========================================================

def load_sent():
    if not os.path.exists(SENT_FILE):
        return {}

    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        print("Error reading sent file:", e)
        return {}


# =========================================================
# SAVE SENT ALERTS
# =========================================================

def save_sent(data):
    try:
        with open(SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False
            )

        return True

    except Exception as e:
        print("Error saving sent file:", e)
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

    encoded_symbol = quote(
        f"NSE:{symbol}",
        safe=""
    )

    return (
        "https://www.tradingview.com/chart/"
        f"?symbol={encoded_symbol}"
    )


# =========================================================
# START
# =========================================================

now = datetime.now(IST)

print()
print("=" * 65)
print("NSE SCANNER V3")
print("UTC TIME :", datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M:%S"))
print("IST TIME :", now.strftime("%d-%b-%Y %H:%M:%S"))
print("=" * 65)


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

    ss.where(
        StockField.HULLMA20 >
        StockField.SIMPLE_MOVING_AVERAGE_50
    )

    ss.set_range(0, 500)

    df = ss.get()

except Exception as e:
    print("First scanner error:", e)
    raise


if df.empty:
    print("No stocks found")
    raise SystemExit


# =========================================================
# SYMBOL CLEANING
# =========================================================

df["Symbol"] = df["Symbol"].apply(clean_symbol)

df = df[df["Symbol"] != ""]

df = df.drop_duplicates(
    subset=["Symbol"],
    keep="first"
)


# =========================================================
# FIND 15 MIN RECOMMENDATION COLUMN
# =========================================================

rating_col = next(
    (
        c for c in df.columns
        if "Recommend" in c and "15" in c
    ),
    None
)

if rating_col is None:
    print("15 minute recommendation column not found.")
    print(df.columns.tolist())
    raise SystemExit


print("Rating column:", rating_col)


# =========================================================
# SIGNAL
# =========================================================

df["Signal"] = df[rating_col].apply(get_signal)

strong_df = df[
    df[rating_col].abs() >= 0.5
].copy()

strong_symbols = strong_df["Symbol"].tolist()

print("Strong Buy/Sell:", len(strong_df))


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

        ss2.where(
            StockField.HULLMA20 >
            StockField.SIMPLE_MOVING_AVERAGE_50
        )

        ss2.where(
            StockField.RELATIVE_STRENGTH_INDEX_14 > 40
        )

        ss2.where(
            StockField.RELATIVE_STRENGTH_INDEX_14 < 70
        )

        ss2.where(
            StockField.RELATIVE_VOLUME > 1
        )

        ss2.set_range(0, 500)

        temp = ss2.get()

        if not temp.empty:
            temp["Symbol"] = temp["Symbol"].apply(clean_symbol)

            temp = temp[temp["Symbol"] != ""]

            temp = temp.drop_duplicates(
                subset=["Symbol"],
                keep="first"
            )

            intraday_df = temp[
                temp["Symbol"].isin(strong_symbols)
            ].copy()

            # Find recommendation column again
            intraday_rating_col = next(
                (
                    c for c in intraday_df.columns
                    if "Recommend" in c and "15" in c
                ),
                None
            )

            if intraday_rating_col:
                intraday_df["Signal"] = (
                    intraday_df[intraday_rating_col]
                    .apply(get_signal)
                )

    except Exception as e:
        print("Intraday scanner error:", e)
        raise


print("Intraday qualified:", len(intraday_df))


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

            if now - last_time < timedelta(
                minutes=COOLDOWN_MINUTES
            ):
                print(symbol, "skipped - cooldown")
                continue

        except Exception as e:
            print(
                "Cooldown parse error:",
                symbol,
                e
            )

    new_alerts.append(row)


# =========================================================
# NO NEW ALERT
# SEND TELEGRAM STATUS MESSAGE
# =========================================================

if not new_alerts:

    print("No new alerts")

    print(
        "Current IST:",
        now.strftime("%d-%b-%Y %H:%M:%S")
    )


    # -----------------------------------------------------
    # NO NEW STOCK MESSAGE
    # -----------------------------------------------------

    no_alert_msg = (

        f"📊 <b>NSE SCAN</b> "
        f"({now.strftime('%d-%b %H:%M')} IST)\n\n"

        f"⚪ <b>NO NEW STOCKS FOUND</b>\n\n"

        f"📌 Strong Buy/Sell: "
        f"<b>{len(strong_df)}</b>\n"

        f"🎯 Intraday Qualified: "
        f"<b>{len(intraday_df)}</b>\n"

        f"🆕 New Alerts: "
        f"<b>0</b>\n\n"

        f"⏱ Cooldown: "
        f"<b>{COOLDOWN_MINUTES} min</b>"
    )


    # -----------------------------------------------------
    # DEBUG
    # -----------------------------------------------------

    print()
    print(
        "Telegram NO NEW STOCK message:"
    )

    print(
        no_alert_msg
    )

    print()


    # -----------------------------------------------------
    # SEND TELEGRAM
    # -----------------------------------------------------

    telegram_success = send_telegram(
        no_alert_msg
    )


    if telegram_success:

        print(
            "Telegram NO NEW STOCK message sent successfully."
        )

    else:

        print(
            "Telegram NO NEW STOCK message failed."
        )


    # -----------------------------------------------------
    # EXIT ONLY AFTER TELEGRAM
    # -----------------------------------------------------

    raise SystemExit


# =========================================================
# TELEGRAM MESSAGE
# =========================================================

msg = (
    f"📊 <b>NSE SCAN</b> "
    f"({now.strftime('%d-%b %H:%M')} IST)\n\n"
)

msg += (
    f"🔥 Strong Buy/Sell: "
    f"<b>{len(strong_df)}</b>\n"
)

msg += (
    f"🎯 Intraday योग्य: "
    f"<b>{len(intraday_df)}</b>\n\n"
)

msg += (
    f"🆕 <b>नए अलर्ट "
    f"({len(new_alerts)}):</b>\n"
)


# =========================================================
# ADD STOCKS
# =========================================================

for row in new_alerts:

    symbol = clean_symbol(row["Symbol"])

    signal = str(
        row.get("Signal", "N/A")
    )

    # RSI
    rsi = row.get(
        "Relative Strength Index (14)",
        "N/A"
    )

    if pd.notna(rsi):
        try:
            rsi = f"{float(rsi):.1f}"
        except Exception:
            rsi = str(rsi)
    else:
        rsi = "N/A"

    # Relative Volume
    rvol = row.get(
        "Relative Volume",
        "N/A"
    )

    if pd.notna(rvol):
        try:
            rvol = f"{float(rvol):.2f}"
        except Exception:
            rvol = str(rvol)
    else:
        rvol = "N/A"

    # TradingView URL
    tv_url = tradingview_link(symbol)

    # Escape visible text for Telegram HTML
    safe_symbol = html.escape(symbol)
    safe_signal = html.escape(signal)

    # Clickable stock symbol
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

print()
print("Telegram message preview:")
print(msg)
print()


# =========================================================
# SEND
# =========================================================

telegram_success = send_telegram(msg)


# =========================================================
# SAVE COOLDOWN AFTER SUCCESS
# =========================================================

if telegram_success:

    for row in new_alerts:

        symbol = clean_symbol(
            row["Symbol"]
        )

        sent[symbol] = now.isoformat()

    save_sent(sent)

    print(
        f"{len(new_alerts)} alerts sent successfully"
    )

else:

    print("Telegram send failed")
    print(
        "sent_alerts.json was not updated"
    )


# =========================================================
# FINISH
# =========================================================

print()
print("=" * 65)
print(
    "Finished IST:",
    now.strftime("%d-%b-%Y %H:%M:%S")
)
print("Strong:", len(strong_df))
print("Intraday:", len(intraday_df))
print("New alerts:", len(new_alerts))
print("=" * 65)
