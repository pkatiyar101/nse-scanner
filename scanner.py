```python
import os
import json
import requests
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from tvscreener import StockScreener, StockField, Market
import pandas as pd


# =========================================================
# CONFIGURATION
# =========================================================

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

SENT_FILE = "sent_alerts.json"

# Same stock will not alert again within this time
COOLDOWN_MINUTES = 60

# IST timezone
IST = timezone(timedelta(hours=5, minutes=30))


# =========================================================
# TELEGRAM SEND FUNCTION
# =========================================================

def send_telegram(msg):

    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram configuration missing")
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

        print(f"Telegram HTTP Status: {response.status_code}")
        print(f"Telegram Response: {response.text}")

        if response.status_code == 200:

            try:
                result = response.json()

                if result.get("ok") is True:
                    print("✅ Telegram message sent successfully")
                    return True

            except Exception:
                pass

        print("❌ Telegram message failed")
        return False

    except Exception as e:

        print(f"❌ Telegram error: {e}")
        return False


# =========================================================
# LOAD SENT ALERTS
# =========================================================

def load_sent():

    if not os.path.exists(SENT_FILE):
        return {}

    try:

        with open(
            SENT_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as e:

        print(f"⚠️ Error reading {SENT_FILE}: {e}")
        return {}


# =========================================================
# SAVE SENT ALERTS
# =========================================================

def save_sent(data):

    try:

        with open(
            SENT_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False
            )

        return True

    except Exception as e:

        print(f"❌ Error saving sent alerts: {e}")
        return False


# =========================================================
# SIGNAL FUNCTION
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
# SYMBOL CLEANING
# =========================================================

def clean_symbol(symbol):

    if pd.isna(symbol):
        return ""

    symbol = str(symbol).strip().upper()

    # Remove exchange prefix
    if ":" in symbol:
        symbol = symbol.split(":")[-1]

    return symbol


# =========================================================
# TRADINGVIEW LINK
# =========================================================

def tradingview_link(symbol):

    symbol = clean_symbol(symbol)

    # URL encode NSE:
    encoded_symbol = quote(
        f"NSE:{symbol}",
        safe=""
    )

    return (
        f"https://www.tradingview.com/chart/"
        f"?symbol={encoded_symbol}"
    )


# =========================================================
# START SCANNER
# =========================================================

now = datetime.now(IST)

print()
print("=" * 70)
print(
    f"🔍 NSE SCANNER STARTED — "
    f"{now.strftime('%d-%b-%Y %H:%M:%S')} IST"
)
print("=" * 70)


# =========================================================
# FIRST SCAN
# HULLMA20 > SMA50
# RECOMMEND ALL 15
# =========================================================

try:

    ss = StockScreener()

    ss.set_markets(
        Market.INDIA
    )

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

    ss.set_range(
        0,
        500
    )

    df = ss.get()

except Exception as e:

    print(f"❌ Screener error: {e}")
    exit()


# =========================================================
# EMPTY CHECK
# =========================================================

if df.empty:

    print("❌ कोई स्टॉक नहीं मिला")
    exit()


print(
    f"📊 Initial stocks found: {len(df)}"
)


# =========================================================
# CLEAN SYMBOL
# =========================================================

df["Symbol"] = df["Symbol"].apply(
    clean_symbol
)

df = df[
    df["Symbol"] != ""
]

df = df.drop_duplicates(
    subset=["Symbol"],
    keep="first"
)


# =========================================================
# FIND RECOMMENDATION COLUMN
# =========================================================

rating_col = next(
    (
        c
        for c in df.columns
        if "Recommend" in c
        and "15" in c
    ),
    None
)


if not rating_col:

    print(
        "⚠️ Recommendation column नहीं मिला."
    )

    print(
        "Available columns:"
    )

    print(
        df.columns.tolist()
    )

    exit()


print(
    f"✅ Rating column: {rating_col}"
)


# =========================================================
# SIGNAL
# =========================================================

df["Signal"] = df[
    rating_col
].apply(get_signal)


# =========================================================
# STRONG BUY / STRONG SELL
# =========================================================

strong_df = df[
    df[rating_col].abs() >= 0.5
].copy()


print(
    f"🔥 Strong Buy/Sell: "
    f"{len(strong_df)}"
)


strong_symbols = (
    strong_df["Symbol"]
    .tolist()
)


# =========================================================
# SECOND / INTRADAY SCAN
# =========================================================

intraday_df = pd.DataFrame()


if strong_symbols:

    try:

        ss2 = StockScreener()

        ss2.set_markets(
            Market.INDIA
        )

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

        # Hull MA 20 > SMA 50
        ss2.where(
            StockField.HULLMA20 >
            StockField.SIMPLE_MOVING_AVERAGE_50
        )

        # RSI 40 - 70
        ss2.where(
            StockField.RELATIVE_STRENGTH_INDEX_14 > 40
        )

        ss2.where(
            StockField.RELATIVE_STRENGTH_INDEX_14 < 70
        )

        # Relative Volume > 1
        ss2.where(
            StockField.RELATIVE_VOLUME > 1
        )

        ss2.set_range(
            0,
            500
        )

        temp = ss2.get()


        if not temp.empty:

            temp["Symbol"] = temp[
                "Symbol"
            ].apply(clean_symbol)

            temp = temp[
                temp["Symbol"] != ""
            ]

            temp = temp.drop_duplicates(
                subset=["Symbol"],
                keep="first"
            )

            # Only Strong Buy / Strong Sell stocks
            intraday_df = temp[
                temp["Symbol"].isin(
                    strong_symbols
                )
            ].copy()


            if rating_col in intraday_df.columns:

                intraday_df["Signal"] = (
                    intraday_df[
                        rating_col
                    ].apply(get_signal)
                )


    except Exception as e:

        print(
            f"❌ Intraday scan error: {e}"
        )


print(
    f"🎯 Intraday योग्य: "
    f"{len(intraday_df)}"
)


# =========================================================
# LOAD PREVIOUS ALERTS
# =========================================================

sent = load_sent()

now = datetime.now(IST)

new_alerts = []


# =========================================================
# COOLDOWN CHECK
# =========================================================

for _, row in intraday_df.iterrows():

    sym = clean_symbol(
        row["Symbol"]
    )

    if not sym:
        continue

    last_sent = sent.get(sym)

    if last_sent:

        try:

            last_time = datetime.fromisoformat(
                last_sent
            )

            # Old file may contain naive datetime
            if last_time.tzinfo is None:

                last_time = last_time.replace(
                    tzinfo=IST
                )

            time_difference = (
                now - last_time
            )

            if (
                time_difference
                < timedelta(
                    minutes=COOLDOWN_MINUTES
                )
            ):

                print(
                    f"⏳ {sym} skipped "
                    f"(cooldown)"
                )

                continue

        except Exception as e:

            print(
                f"⚠️ Time parse error "
                f"for {sym}: {e}"
            )


    new_alerts.append(row)


# =========================================================
# NO NEW ALERT
# =========================================================

if not new_alerts:

    print()
    print(
        "✅ कोई नया अलर्ट नहीं"
    )

    print(
        f"⏰ Current IST: "
        f"{now.strftime('%d-%b-%Y %H:%M:%S')}"
    )

    exit()


# =========================================================
# BUILD TELEGRAM MESSAGE
# =========================================================

msg = (
    f"📊 <b>NSE SCAN</b>\n"
    f"⏰ {now.strftime('%d-%b-%Y %H:%M:%S')} IST\n"
    f"\n"
)

msg += (
    f"🔥 Strong Buy/Sell: "
    f"<b>{len(strong_df)}</b>\n"
)

msg += (
    f"🎯 Intraday योग्य: "
    f"<b>{len(intraday_df)}</b>\n"
)

msg += (
    f"🆕 New Alerts: "
    f"<b>{len(new_alerts)}</b>\n"
)

msg += "\n"


# =========================================================
# ADD STOCK ALERTS
# =========================================================

for row in new_alerts:

    symbol = clean_symbol(
        row["Symbol"]
    )

    signal = row.get(
        "Signal",
        "N/A"
    )


    # ---------------------------------------------
    # RSI
    # ---------------------------------------------

    rsi = row.get(
        "Relative Strength Index (14)",
        "N/A"
    )


    if pd.isna(rsi):

        rsi = "N/A"

    else:

        try:

            rsi = f"{float(rsi):.1f}"

        except Exception:

            rsi = str(rsi)


    # ---------------------------------------------
    # Price
    # ---------------------------------------------

    price = row.get(
        "Price",
        "N/A"
    )


    if pd.notna(price):

        try:

            price = f"{float(price):.2f}"

        except Exception:

            price = str(price)

    else:

        price = "N/A"


    # ---------------------------------------------
    # Change %
    # ---------------------------------------------

    change = row.get(
        "Change %",
        row.get(
            "Change Percent",
            "N/A"
        )
    )


    if pd.notna(change):

        try:

            change = f"{float(change):+.2f}%"

        except Exception:

            change = str(change)

    else:

        change = "N/A"


    # ---------------------------------------------
    # Relative Volume
    # ---------------------------------------------

    rel_volume = row.get(
        "Relative Volume",
        "N/A"
    )


    if pd.notna(rel_volume):

        try:

            rel_volume = (
                f"{float(rel_volume):.2f}"
            )

        except Exception:

            rel_volume = str(rel_volume)

    else:

        rel_volume = "N/A"


    # ---------------------------------------------
    # TradingView hyperlink
    # ---------------------------------------------

    tv_link = tradingview_link(
        symbol
    )


    # ---------------------------------------------
    # Telegram line
    # ---------------------------------------------

    msg += (
        f'🔹 <a href="{tv_link}">'
        f"<b>{symbol}</b>"
        f"</a>"
        f" — <b>{signal}</b>"
        f" | RSI: {rsi}"
        f" | RVOL: {rel_volume}"
        f"\n"
    )


# =========================================================
# SEND TELEGRAM
# =========================================================

print()
print("📤 Sending Telegram message...")

telegram_success = send_telegram(
    msg
)


# =========================================================
# SAVE COOLDOWN ONLY AFTER SUCCESSFUL SEND
# =========================================================

if telegram_success:

    for row in new_alerts:

        sym = clean_symbol(
            row["Symbol"]
        )

        sent[sym] = now.isoformat()


    save_sent(sent)

    print()
    print(
        f"✅ {len(new_alerts)} "
        f"alerts sent successfully"
    )

else:

    print()
    print(
        "❌ Telegram send failed."
    )

    print(
        "⚠️ sent_alerts.json "
        "update नहीं किया गया."
    )


# =========================================================
# FINAL STATUS
# =========================================================

print()
print("=" * 70)

print(
    f"⏰ Finished: "
    f"{now.strftime('%d-%b-%Y %H:%M:%S')} IST"
)

print(
    f"🔥 Strong: {len(strong_df)}"
)

print(
    f"🎯 Intraday: {len(intraday_df)}"
)

print(
    f"🆕 New alerts: {len(new_alerts)}"
)

print("=" * 70)
```

### Telegram में output अब इस प्रकार आएगा

```text
📊 NSE SCAN
⏰ 23-Sep-2026 16:42:35 IST

🔥 Strong Buy/Sell: 18
🎯 Intraday योग्य: 7
🆕 New Alerts: 3

🔹 RELIANCE — STRONG BUY | RSI: 62.4 | RVOL: 1.85
🔹 TATASTEEL — STRONG BUY | RSI: 58.7 | RVOL: 2.14
🔹 INFY — STRONG SELL | RSI: 43.2 | RVOL: 1.42
```

**Symbol पर click करने पर TradingView NSE chart खुलेगा।**

एक खास सुधार यह है कि अब `sent_alerts.json` **Telegram message सफल होने के बाद ही update होगा**। इसलिए Telegram में error आने पर आपका 60-minute cooldown गलत तरीके से consume नहीं होगा।
