# =========================================================
# CRYPTO SCREENER + TELEGRAM ALERT
# =========================================================

# For Jupyter / Colab only:
# !pip install tvscreener -q


# =========================================================
# IMPORTS
# =========================================================

import os
import json
import html
import requests

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd

from tvscreener import CryptoScreener, CryptoField


# =========================================================
# VERSION
# =========================================================

print("====================================================")
print("CRYPTO SCANNER V1")
print("TELEGRAM + TRADINGVIEW + IST")
print("====================================================")


# =========================================================
# TELEGRAM CONFIGURATION
# =========================================================

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Separate file for Crypto alerts
SENT_FILE = "crypto_sent_alerts.json"

# Same coin will not alert again within 60 minutes
COOLDOWN_MINUTES = 60


# =========================================================
# IST TIMEZONE
# =========================================================

IST = timezone(
    timedelta(hours=5, minutes=30)
)


# =========================================================
# TELEGRAM SEND
# =========================================================

def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:

        print("⚠️ Telegram configuration missing")
        print(message)

        return False


    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )


    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }


    try:

        response = requests.post(
            url,
            data=payload,
            timeout=15
        )


        print(
            "Telegram HTTP Status:",
            response.status_code
        )


        print(
            "Telegram Response:",
            response.text
        )


        if response.status_code == 200:

            result = response.json()

            if result.get("ok") is True:

                print(
                    "✅ Telegram message sent successfully"
                )

                return True


        print(
            "❌ Telegram message failed"
        )

        return False


    except Exception as e:

        print(
            "❌ Telegram error:",
            e
        )

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

        print(
            "⚠️ Error reading sent file:",
            e
        )

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

        print(
            "❌ Error saving sent file:",
            e
        )

        return False


# =========================================================
# SIGNAL FUNCTION
# =========================================================

def get_signal(value):

    if pd.isna(value):

        return "NEUTRAL"


    try:

        value = float(value)

    except Exception:

        return "NEUTRAL"


    if value >= 0.5:

        return "STRONG BUY"


    elif value >= 0.1:

        return "BUY"


    elif value <= -0.5:

        return "STRONG SELL"


    elif value <= -0.1:

        return "SELL"


    else:

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

    symbol = str(symbol).strip().upper()


    # If screener already returns exchange:symbol
    if ":" in symbol:

        tv_symbol = symbol

    else:

        # Default crypto exchange
        tv_symbol = f"BINANCE:{symbol}"


    encoded = quote(
        tv_symbol,
        safe=""
    )


    return (
        "https://www.tradingview.com/chart/"
        f"?symbol={encoded}"
    )


# =========================================================
# CURRENT IST TIME
# =========================================================

now = datetime.now(IST)


print()

print(
    "UTC TIME :",
    datetime.now(timezone.utc)
    .strftime("%d-%b-%Y %H:%M:%S")
)


print(
    "IST TIME :",
    now.strftime("%d-%b-%Y %H:%M:%S")
)


# =========================================================
# STEP 1
# STRONG BUY / STRONG SELL
# =========================================================

print()
print(
    "🔍 STEP 1: Strong coins scanning..."
)


cs = CryptoScreener()


cs.select(

    CryptoField.NAME,

    CryptoField.PRICE,

    CryptoField.HULLMA20,

    CryptoField.SIMPLE_MOVING_AVERAGE_50,

    CryptoField.RECOMMEND_ALL_15,

)


# Hull MA20 > SMA50

cs.where(

    CryptoField.HULLMA20 >

    CryptoField.SIMPLE_MOVING_AVERAGE_50

)


cs.set_range(
    0,
    500
)


df = cs.get()


print(
    "Total coins scanned:",
    len(df)
)


# =========================================================
# CREATE STRONG DATAFRAME
# =========================================================

strong_df = pd.DataFrame()


if not df.empty:


    # -----------------------------------------------
    # Find recommendation column
    # -----------------------------------------------

    rating_col = None


    for col in df.columns:

        if (
            "Recommend" in col
            and "15" in col
        ):

            rating_col = col

            break


    if rating_col is not None:


        # -------------------------------------------
        # Strong Buy / Strong Sell
        # -------------------------------------------

        strong_df = df[

            (df[rating_col] >= 0.5)

            |

            (df[rating_col] <= -0.5)

        ].copy()


        # -------------------------------------------
        # Signal
        # -------------------------------------------

        strong_df["Signal"] = (

            strong_df[rating_col]

            .apply(get_signal)

        )


        # -------------------------------------------
        # Clean Symbol
        # -------------------------------------------

        if "Symbol" in strong_df.columns:

            strong_df["Symbol"] = (

                strong_df["Symbol"]

                .astype(str)

                .str.split(":")

                .str[-1]

            )


        # -------------------------------------------
        # Remove duplicates
        # -------------------------------------------

        if "Symbol" in strong_df.columns:

            strong_df = (

                strong_df

                .drop_duplicates(

                    subset=["Symbol"],

                    keep="first"

                )

            )


        # -------------------------------------------
        # Sort
        # -------------------------------------------

        strong_df = (

            strong_df

            .sort_values(

                by=rating_col,

                ascending=False,

                na_position="last"

            )

            .reset_index(drop=True)

        )


print(
    "🔥 Strong Buy/Sell:",
    len(strong_df)
)


# =========================================================
# STRONG SYMBOL LIST
# =========================================================

if strong_df.empty:

    print(
        "⚠️ Strong Buy/Sell coins nahi mile."
    )

    raise SystemExit


strong_symbols = (

    strong_df["Symbol"]

    .tolist()

)


# =========================================================
# STEP 2
# INTRADAY SCAN
# =========================================================

print()

print(
    "🔍 STEP 2: Intraday scanning "
    "(Strong coins me se)..."
)


cs2 = CryptoScreener()


cs2.select(

    CryptoField.NAME,

    CryptoField.PRICE,

    CryptoField.CHANGE_PERCENT,

    CryptoField.VOLUME,

    CryptoField.RELATIVE_VOLUME,

    CryptoField.RELATIVE_STRENGTH_INDEX_14,

    CryptoField.HULLMA20,

    CryptoField.SIMPLE_MOVING_AVERAGE_50,

    CryptoField.RECOMMEND_ALL_15,

)


# =========================================================
# INTRADAY CONDITIONS
# =========================================================


# Hull MA20 > SMA50

cs2.where(

    CryptoField.HULLMA20 >

    CryptoField.SIMPLE_MOVING_AVERAGE_50

)


# RSI > 40

cs2.where(

    CryptoField.RELATIVE_STRENGTH_INDEX_14 > 40

)


# RSI < 70

cs2.where(

    CryptoField.RELATIVE_STRENGTH_INDEX_14 < 70

)


# Relative Volume > 1

cs2.where(

    CryptoField.RELATIVE_VOLUME > 1

)


cs2.set_range(
    0,
    500
)


intraday_df = cs2.get()


# =========================================================
# CHECK RESULT
# =========================================================

if intraday_df.empty:

    print(
        "⚠️ Intraday conditions me "
        "koi coin nahi mila."
    )

    raise SystemExit


# =========================================================
# CLEAN SYMBOL
# =========================================================

intraday_df["Symbol"] = (

    intraday_df["Symbol"]

    .astype(str)

    .str.split(":")

    .str[-1]

)


# =========================================================
# REMOVE DUPLICATES
# =========================================================

intraday_df = (

    intraday_df

    .drop_duplicates(

        subset=["Symbol"],

        keep="first"

    )

)


# =========================================================
# ONLY STRONG COINS
# =========================================================

intraday_df = intraday_df[

    intraday_df["Symbol"].isin(
        strong_symbols
    )

].copy()


# =========================================================
# FINAL CHECK
# =========================================================

if intraday_df.empty:

    print(
        "⚠️ Strong coins me se koi bhi "
        "intraday conditions pass nahi kar paya."
    )

    raise SystemExit


# =========================================================
# FIND RATING COLUMN
# =========================================================

rating_col2 = None


for col in intraday_df.columns:

    if (
        "Recommend" in col
        and "15" in col
    ):

        rating_col2 = col

        break


# =========================================================
# SIGNAL
# =========================================================

if rating_col2:

    intraday_df["Signal"] = (

        intraday_df[rating_col2]

        .apply(get_signal)

    )


# =========================================================
# SORT
# =========================================================

intraday_df = (

    intraday_df

    .sort_values(

        by=rating_col2

        if rating_col2

        else "Symbol",

        ascending=False,

        na_position="last"

    )

    .reset_index(drop=True)

)


print()

print(
    "🎯 STEP 2 RESULT:",
    len(intraday_df),
    "coins"
)


# =========================================================
# LOAD COOLDOWN FILE
# =========================================================

sent = load_sent()


# =========================================================
# NEW ALERTS
# =========================================================

new_alerts = []


now = datetime.now(IST)


for _, row in intraday_df.iterrows():

    symbol = clean_symbol(
        row["Symbol"]
    )


    if not symbol:

        continue


    last_sent = sent.get(symbol)


    if last_sent:

        try:

            last_time = datetime.fromisoformat(
                last_sent
            )


            if last_time.tzinfo is None:

                last_time = last_time.replace(
                    tzinfo=IST
                )


            difference = (
                now - last_time
            )


            if difference < timedelta(
                minutes=COOLDOWN_MINUTES
            ):

                print(
                    f"⏳ {symbol} skipped "
                    f"(60 min cooldown)"
                )

                continue


        except Exception as e:

            print(
                "Cooldown error:",
                symbol,
                e
            )


    new_alerts.append(row)


# =========================================================
# NO NEW ALERT
# =========================================================

if not new_alerts:

    print()

    print(
        "✅ कोई नया Crypto alert नहीं"
    )

    print(
        "Current IST:",
        now.strftime(
            "%d-%b-%Y %H:%M:%S"
        )
    )

    raise SystemExit


# =========================================================
# TELEGRAM HEADER
# =========================================================

msg = (

    f"🪙 <b>CRYPTO SCAN</b>\n"

    f"⏰ "
    f"{now.strftime('%d-%b-%Y %H:%M:%S')}"
    f" IST\n\n"

    f"🔥 Strong Buy/Sell: "
    f"<b>{len(strong_df)}</b>\n"

    f"🎯 Intraday योग्य: "
    f"<b>{len(intraday_df)}</b>\n\n"

    f"🆕 <b>New Crypto Alerts "
    f"({len(new_alerts)}):</b>\n"

)


# =========================================================
# ADD COINS TO TELEGRAM
# =========================================================

for _, row in pd.DataFrame(new_alerts).iterrows():

    symbol = clean_symbol(
        row["Symbol"]
    )


    signal = row.get(
        "Signal",
        "N/A"
    )


    # -----------------------------------------------
    # RSI
    # -----------------------------------------------

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


    # -----------------------------------------------
    # Price
    # -----------------------------------------------

    price = row.get(
        "Price",
        "N/A"
    )


    if pd.notna(price):

        try:

            price = f"{float(price):.6f}"

        except Exception:

            price = str(price)

    else:

        price = "N/A"


    # -----------------------------------------------
    # Change %
    # -----------------------------------------------

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


    # -----------------------------------------------
    # Relative Volume
    # -----------------------------------------------

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


    # -----------------------------------------------
    # TradingView
    # -----------------------------------------------

    tv_url = tradingview_link(
        symbol
    )


    # -----------------------------------------------
    # Escape visible text
    # -----------------------------------------------

    safe_symbol = html.escape(
        symbol
    )

    safe_signal = html.escape(
        str(signal)
    )


    # -----------------------------------------------
    # Clickable coin
    # -----------------------------------------------

    msg += (

        f'🔹 <a href="{tv_url}">'
        f'<b>{safe_symbol}</b>'
        f'</a>'

        f' — <b>{safe_signal}</b>'

        f' | RSI: {rsi}'

        f' | RVOL: {rvol}'

        f' | Chg: {change}'

        f' | Price: {price}'

        f'\n'

    )


# =========================================================
# TELEGRAM PREVIEW
# =========================================================

print()
print(
    "========== TELEGRAM MESSAGE =========="
)

print(msg)

print(
    "======================================="
)

print()


# =========================================================
# SEND TELEGRAM
# =========================================================

telegram_success = send_telegram(
    msg
)


# =========================================================
# SAVE ONLY AFTER SUCCESS
# =========================================================

if telegram_success:


    for _, row in intraday_df.iterrows():

        symbol = clean_symbol(
            row["Symbol"]
        )


        # Only save alerts actually sent
        if any(
            clean_symbol(x["Symbol"]) == symbol
            for x in new_alerts
        ):

            sent[symbol] = (
                now.isoformat()
            )


    save_sent(sent)


    print()

    print(
        f"✅ {len(new_alerts)} "
        f"Crypto alerts sent."
    )


else:

    print()

    print(
        "❌ Telegram failed."
    )

    print(
        "⚠️ Cooldown file not updated."
    )


# =========================================================
# FINAL SUMMARY
# =========================================================

print()

print("=" * 60)

print(
    "📊 FINAL SUMMARY"
)

print(
    "Total scanned coins      :",
    len(df)
)

print(
    "Strong Buy/Sell coins    :",
    len(strong_df)
)

print(
    "Intraday qualified coins :",
    len(intraday_df)
)

print(
    "New Telegram alerts      :",
    len(new_alerts)
)

print(
    "IST                      :",
    now.strftime(
        "%d-%b-%Y %H:%M:%S"
    )
)

print("=" * 60)
