print("==============================================================")
print("===== NSE SCANNER VERSION 2026-09-25-FINAL-DUAL-TF =====")
print("===== DAILY + 15 MIN BUY/SELL + TELEGRAM =====")
print("==============================================================")


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

from tvscreener import (
    StockScreener,
    StockField,
    Market
)


# =========================================================
# CONFIGURATION
# =========================================================

BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN"
)

CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID"
)

SENT_FILE = "sent_alerts.json"

# Same stock can alert again after 5 minutes
COOLDOWN_MINUTES = 5

# RSI range
RSI_MIN = 40
RSI_MAX = 70

# Relative Volume
RVOL_MIN = 1

# Maximum rows per request
PAGE_SIZE = 500


# =========================================================
# INDIA STANDARD TIME
# =========================================================

IST = timezone(
    timedelta(
        hours=5,
        minutes=30
    )
)


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(msg):

    if not BOT_TOKEN or not CHAT_ID:

        print("ERROR: Telegram configuration missing")

        print(msg)

        return False


    # IMPORTANT:
    # Do NOT put Markdown brackets in this URL

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )


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
                    "Telegram message sent successfully"
                )

                return True


        print(
            "Telegram message failed"
        )

        return False


    except Exception as e:

        print(
            "Telegram error:",
            repr(e)
        )

        return False


# =========================================================
# LOAD SENT ALERTS
# =========================================================

def load_sent():

    if not os.path.exists(
        SENT_FILE
    ):

        return {}


    try:

        with open(
            SENT_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)


        if isinstance(
            data,
            dict
        ):

            return data


        return {}


    except Exception as e:

        print(
            "Error reading sent file:",
            repr(e)
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
            "Error saving sent file:",
            repr(e)
        )

        return False


# =========================================================
# CLEAN SYMBOL
# =========================================================

def clean_symbol(symbol):

    if pd.isna(symbol):

        return ""


    symbol = str(
        symbol
    ).strip().upper()


    if ":" in symbol:

        symbol = symbol.split(
            ":"
        )[-1]


    return symbol


# =========================================================
# TRADINGVIEW LINK
# =========================================================

def tradingview_link(symbol):

    symbol = clean_symbol(
        symbol
    )


    encoded_symbol = quote(

        f"NSE:{symbol}",

        safe=""
    )


    return (

        "https://www.tradingview.com/chart/"
        f"?symbol={encoded_symbol}"

    )


# =========================================================
# SIGNAL
# =========================================================

def get_signal(value):

    if pd.isna(value):

        return "NEUTRAL"


    try:

        value = float(
            value
        )

    except Exception:

        return "NEUTRAL"


    if value >= 0.5:

        return "STRONG BUY"


    if value >= 0.1:

        return "BUY"


    if value <= -0.5:

        return "STRONG SELL"


    if value <= -0.1:

        return "SELL"


    return "NEUTRAL"


# =========================================================
# FIND COLUMN
# =========================================================

def find_column(
    df,
    keyword_list
):

    if df is None:

        return None


    if df.empty:

        return None


    for column in df.columns:

        text = str(
            column
        ).lower()


        if all(

            str(keyword).lower()
            in text

            for keyword in keyword_list

        ):

            return column


    return None


# =========================================================
# PRINT COLUMNS
# =========================================================

def print_columns(
    title,
    df
):

    print()
    print(
        "-----",
        title,
        "-----"
    )


    if df is None or df.empty:

        print(
            "No columns - DataFrame empty"
        )

        return


    for column in df.columns:

        print(
            column
        )


# =========================================================
# PREPARE SYMBOL
# =========================================================

def prepare_symbols(df):

    if df is None:

        return pd.DataFrame()


    if df.empty:

        return df


    if "Symbol" not in df.columns:

        print(
            "ERROR: Symbol column not found"
        )

        print(
            df.columns.tolist()
        )

        return pd.DataFrame()


    df = df.copy()


    df["Symbol"] = (
        df["Symbol"]
        .apply(clean_symbol)
    )


    df = df[
        df["Symbol"] != ""
    ]


    df = df.drop_duplicates(

        subset=["Symbol"],

        keep="first"
    )


    return df


# =========================================================
# GET DAILY DATA
# =========================================================

def get_daily_data():

    print()
    print(
        "================================================"
    )

    print(
        "STEP 1 : DAILY DATA"
    )

    print(
        "================================================"
    )


    try:

        ss = StockScreener()


        ss.set_markets(
            Market.INDIA
        )


        # IMPORTANT:
        # Do NOT compare HULLMA20 and SMA50
        # inside where().
        #
        # We retrieve both fields and compare
        # them later using Pandas.

        ss.select(

            StockField.NAME,

            StockField.PRICE,

            StockField.HULLMA20,

            StockField.SIMPLE_MOVING_AVERAGE_50,

            StockField.RECOMMEND_ALL_15
        )


        ss.set_range(
            0,
            PAGE_SIZE
        )


        df = ss.get()


        print(
            "Daily raw rows:",
            len(df)
        )


        if df.empty:

            return pd.DataFrame()


        print_columns(
            "DAILY COLUMNS",
            df
        )


        return prepare_symbols(
            df
        )


    except Exception as e:

        print(
            "DAILY DATA ERROR:",
            repr(e)
        )

        raise


# =========================================================
# DAILY BUY / SELL
# =========================================================

def process_daily(df):

    print()
    print(
        "================================================"
    )

    print(
        "STEP 1 : DAILY BUY / SELL"
    )

    print(
        "================================================"
    )


    if df.empty:

        return (
            pd.DataFrame(),
            pd.DataFrame()
        )


    hull_col = find_column(

        df,

        ["hull", "20"]

    )


    sma_col = find_column(

        df,

        ["sma", "50"]

    )


    print(
        "Daily HULL column:",
        hull_col
    )


    print(
        "Daily SMA column:",
        sma_col
    )


    if hull_col is None:

        print(
            "ERROR: Daily HULLMA20 column not found"
        )

        return (
            pd.DataFrame(),
            pd.DataFrame()
        )


    if sma_col is None:

        print(
            "ERROR: Daily SMA50 column not found"
        )

        return (
            pd.DataFrame(),
            pd.DataFrame()
        )


    # Convert to numeric

    df[hull_col] = pd.to_numeric(

        df[hull_col],

        errors="coerce"
    )


    df[sma_col] = pd.to_numeric(

        df[sma_col],

        errors="coerce"
    )


    # -----------------------------------------------------
    # DAILY BUY
    # HULLMA20 > SMA50
    # -----------------------------------------------------

    daily_buy_df = df[

        df[hull_col]
        >
        df[sma_col]

    ].copy()


    # -----------------------------------------------------
    # DAILY SELL
    # HULLMA20 < SMA50
    # -----------------------------------------------------

    daily_sell_df = df[

        df[hull_col]
        <
        df[sma_col]

    ].copy()


    print(
        "Daily BUY candidates:",
        len(daily_buy_df)
    )


    print(
        "Daily SELL candidates:",
        len(daily_sell_df)
    )


    return (
        daily_buy_df,
        daily_sell_df
    )


# =========================================================
# GET 15 MIN DATA
# =========================================================

def get_15min_data():

    print()
    print(
        "================================================"
    )

    print(
        "STEP 2 : 15 MIN DATA"
    )

    print(
        "================================================"
    )


    try:

        ss = StockScreener()


        ss.set_markets(
            Market.INDIA
        )


        # -------------------------------------------------
        # 15 MIN TECHNICAL FIELDS
        # -------------------------------------------------

        HULLMA20_15 = (

            StockField.HULLMA20
            .with_interval("15")

        )


        SMA50_15 = (

            StockField.SIMPLE_MOVING_AVERAGE_50
            .with_interval("15")

        )


        RSI14_15 = (

            StockField.RELATIVE_STRENGTH_INDEX_14
            .with_interval("15")

        )


        # -------------------------------------------------
        # IMPORTANT
        #
        # Keep Relative Volume as standard field
        # for compatibility.
        # -------------------------------------------------

        RVOL_FIELD = (
            StockField.RELATIVE_VOLUME
        )


        ss.select(

            StockField.NAME,

            StockField.PRICE,

            StockField.CHANGE_PERCENT,

            StockField.VOLUME,

            RVOL_FIELD,

            RSI14_15,

            HULLMA20_15,

            SMA50_15,

            StockField.RECOMMEND_ALL_15
        )


        ss.set_range(
            0,
            PAGE_SIZE
        )


        df = ss.get()


        print(
            "15m raw rows:",
            len(df)
        )


        if df.empty:

            return pd.DataFrame()


        print_columns(
            "15 MIN COLUMNS",
            df
        )


        return prepare_symbols(
            df
        )


    except Exception as e:

        print(
            "15 MIN DATA ERROR:",
            repr(e)
        )

        raise


# =========================================================
# PROCESS 15 MIN BUY / SELL
# =========================================================

def process_15min(
    df,
    daily_buy_symbols,
    daily_sell_symbols
):

    print()
    print(
        "================================================"
    )

    print(
        "STEP 2 : 15 MIN BUY / SELL"
    )

    print(
        "================================================"
    )


    if df.empty:

        return (

            pd.DataFrame(),

            pd.DataFrame()

        )


    # -----------------------------------------------------
    # FIND COLUMNS
    # -----------------------------------------------------

    hull_col = find_column(

        df,

        ["hull", "20"]

    )


    sma_col = find_column(

        df,

        ["sma", "50"]

    )


    rsi_col = find_column(

        df,

        ["rsi"]

    )


    rvol_col = find_column(

        df,

        ["relative", "volume"]

    )


    rating_col = next(

        (

            column

            for column in df.columns

            if (

                "recommend"
                in str(column).lower()

                and

                "15"
                in str(column).lower()

            )

        ),

        None

    )


    print(
        "15m HULL column:",
        hull_col
    )


    print(
        "15m SMA column:",
        sma_col
    )


    print(
        "15m RSI column:",
        rsi_col
    )


    print(
        "15m RVOL column:",
        rvol_col
    )


    print(
        "15m Rating column:",
        rating_col
    )


    if hull_col is None:

        raise RuntimeError(
            "15m HULLMA20 column not found"
        )


    if sma_col is None:

        raise RuntimeError(
            "15m SMA50 column not found"
        )


    if rsi_col is None:

        raise RuntimeError(
            "15m RSI column not found"
        )


    if rvol_col is None:

        raise RuntimeError(
            "Relative Volume column not found"
        )


    if rating_col is None:

        raise RuntimeError(
            "Recommend All|15 column not found"
        )


    # -----------------------------------------------------
    # NUMERIC CONVERSION
    # -----------------------------------------------------

    df[hull_col] = pd.to_numeric(

        df[hull_col],

        errors="coerce"
    )


    df[sma_col] = pd.to_numeric(

        df[sma_col],

        errors="coerce"
    )


    df[rsi_col] = pd.to_numeric(

        df[rsi_col],

        errors="coerce"
    )


    df[rvol_col] = pd.to_numeric(

        df[rvol_col],

        errors="coerce"
    )


    df[rating_col] = pd.to_numeric(

        df[rating_col],

        errors="coerce"
    )


    # =====================================================
    # COMMON 15 MIN CONDITIONS
    # =====================================================

    common = df[

        (df[rsi_col] > RSI_MIN)

        &

        (df[rsi_col] < RSI_MAX)

        &

        (df[rvol_col] > RVOL_MIN)

    ].copy()


    print(
        "15m after RSI + RVOL:",
        len(common)
    )


    # =====================================================
    # 15 MIN BUY
    #
    # HULLMA20 > SMA50
    # RSI 40-70
    # RVOL > 1
    # Recommend >= 0.5
    # AND Daily BUY
    # =====================================================

    buy_df = common[

        (common[hull_col] > common[sma_col])

        &

        (common[rating_col] >= 0.5)

        &

        (common["Symbol"].isin(
            daily_buy_symbols
        ))

    ].copy()


    # =====================================================
    # 15 MIN SELL
    #
    # HULLMA20 < SMA50
    # RSI 40-70
    # RVOL > 1
    # Recommend <= -0.5
    # AND Daily SELL
    # =====================================================

    sell_df = common[

        (common[hull_col] < common[sma_col])

        &

        (common[rating_col] <= -0.5)

        &

        (common["Symbol"].isin(
            daily_sell_symbols
        ))

    ].copy()


    # -----------------------------------------------------
    # SIGNAL
    # -----------------------------------------------------

    buy_df["Signal"] = (
        "STRONG BUY"
    )


    sell_df["Signal"] = (
        "STRONG SELL"
    )


    print()
    print(
        "15m STRONG BUY:",
        len(buy_df)
    )


    print(
        "15m STRONG SELL:",
        len(sell_df)
    )


    return (
        buy_df,
        sell_df
    )


# =========================================================
# FORMAT NUMBER
# =========================================================

def format_rsi(value):

    try:

        return f"{float(value):.1f}"

    except Exception:

        return "N/A"


def format_rvol(value):

    try:

        return f"{float(value):.2f}"

    except Exception:

        return "N/A"


def format_price(value):

    try:

        return f"₹{float(value):,.2f}"

    except Exception:

        return "N/A"


# =========================================================
# COOLDOWN
# =========================================================

def apply_cooldown(
    df,
    sent,
    now
):

    if df.empty:

        return []


    new_alerts = []


    for _, row in df.iterrows():

        symbol = clean_symbol(
            row["Symbol"]
        )


        if not symbol:

            continue


        # Use symbol + signal
        # so BUY and SELL are treated separately

        signal = str(

            row.get(
                "Signal",
                ""
            )

        ).upper()


        alert_key = (
            f"{symbol}_{signal}"
        )


        last_sent = sent.get(
            alert_key
        )


        if last_sent:

            try:

                last_time = datetime.fromisoformat(
                    last_sent
                )


                if last_time.tzinfo is None:

                    last_time = last_time.replace(
                        tzinfo=IST
                    )


                elapsed = (
                    now - last_time
                )


                if elapsed < timedelta(
                    minutes=COOLDOWN_MINUTES
                ):

                    print(
                        symbol,
                        signal,
                        "SKIPPED - COOLDOWN"
                    )

                    continue


            except Exception as e:

                print(
                    "Cooldown parse error:",
                    symbol,
                    repr(e)
                )


        new_alerts.append(
            row
        )


    return new_alerts


# =========================================================
# CREATE STATUS MESSAGE
# =========================================================

def create_no_alert_message(

    now,

    daily_buy_count,

    daily_sell_count,

    buy_count,

    sell_count

):

    return (

        f"📊 <b>NSE SCAN</b> — "
        f"{now.strftime('%d-%b %H:%M')} IST\n\n"

        f"⚪ <b>NEW STOCKS NOT MATCH "
        f"AS PER CONDITION</b>\n\n"

        f"📈 Daily BUY candidates: "
        f"<b>{daily_buy_count}</b>\n"

        f"📉 Daily SELL candidates: "
        f"<b>{daily_sell_count}</b>\n"

        f"🔥 15m Strong BUY: "
        f"<b>{buy_count}</b>\n"

        f"🎯 15m Strong SELL: "
        f"<b>{sell_count}</b>\n"

        f"🆕 New Alerts: "
        f"<b>0</b>"

    )


# =========================================================
# CREATE TELEGRAM ALERT
# =========================================================

def create_alert_message(

    now,

    buy_alerts,

    sell_alerts,

    daily_buy_count,

    daily_sell_count,

    buy_count,

    sell_count,

    rsi_col,

    rvol_col,

    price_col

):

    msg = (

        f"📊 <b>NSE SCAN</b> — "
        f"{now.strftime('%d-%b %H:%M')} IST\n\n"

    )


    # =====================================================
    # STRONG BUY
    # =====================================================

    msg += (
        "🔥 <b>STRONG BUY</b>\n\n"
    )


    if buy_alerts:

        for row in buy_alerts:

            symbol = clean_symbol(
                row["Symbol"]
            )


            rsi = (
                row.get(
                    rsi_col,
                    "N/A"
                )

                if rsi_col

                else "N/A"
            )


            rvol = (
                row.get(
                    rvol_col,
                    "N/A"
                )

                if rvol_col

                else "N/A"
            )


            price = (
                row.get(
                    price_col,
                    "N/A"
                )

                if price_col

                else "N/A"
            )


            tv_url = tradingview_link(
                symbol
            )


            safe_symbol = html.escape(
                symbol
            )


            msg += (

                f"• <b>{safe_symbol}</b>\n"

                f"  RSI: "
                f"{format_rsi(rsi)}\n"

                f"  RVOL: "
                f"{format_rvol(rvol)}\n"

                f"  Price: "
                f"{format_price(price)}\n"

                f'  📈 <a href="{tv_url}">'
                f"TradingView"
                f"</a>\n\n"

            )


    else:

        msg += (
            "• No Strong Buy alerts\n\n"
        )


    # =====================================================
    # STRONG SELL
    # =====================================================

    msg += (
        "🎯 <b>STRONG SELL</b>\n\n"
    )


    if sell_alerts:

        for row in sell_alerts:

            symbol = clean_symbol(
                row["Symbol"]
            )


            rsi = (
                row.get(
                    rsi_col,
                    "N/A"
                )

                if rsi_col

                else "N/A"
            )


            rvol = (
                row.get(
                    rvol_col,
                    "N/A"
                )

                if rvol_col

                else "N/A"
            )


            price = (
                row.get(
                    price_col,
                    "N/A"
                )

                if price_col

                else "N/A"
            )


            tv_url = tradingview_link(
                symbol
            )


            safe_symbol = html.escape(
                symbol
            )


            msg += (

                f"• <b>{safe_symbol}</b>\n"

                f"  RSI: "
                f"{format_rsi(rsi)}\n"

                f"  RVOL: "
                f"{format_rvol(rvol)}\n"

                f"  Price: "
                f"{format_price(price)}\n"

                f'  📉 <a href="{tv_url}">'
                f"TradingView"
                f"</a>\n\n"

            )


    else:

        msg += (
            "• No Strong Sell alerts\n\n"
        )


    # =====================================================
    # SUMMARY
    # =====================================================

    msg += (

        f"📈 Daily BUY: "
        f"<b>{daily_buy_count}</b>\n"

        f"📉 Daily SELL: "
        f"<b>{daily_sell_count}</b>\n"

        f"🔥 15m Strong BUY: "
        f"<b>{buy_count}</b>\n"

        f"🎯 15m Strong SELL: "
        f"<b>{sell_count}</b>\n"

        f"🆕 New Alerts: "
        f"<b>{len(buy_alerts) + len(sell_alerts)}</b>"

    )


    return msg


# =========================================================
# MAIN
# =========================================================

def main():

    now = datetime.now(
        IST
    )


    print()
    print(
        "=" * 70
    )


    print(
        "NSE SCANNER"
    )


    print(
        "UTC TIME:",
        datetime.now(
            timezone.utc
        ).strftime(
            "%d-%b-%Y %H:%M:%S"
        )
    )


    print(
        "IST TIME:",
        now.strftime(
            "%d-%b-%Y %H:%M:%S"
        )
    )


    print(
        "COOLDOWN:",
        COOLDOWN_MINUTES,
        "minutes"
    )


    print(
        "RSI:",
        RSI_MIN,
        "-",
        RSI_MAX
    )


    print(
        "RVOL:",
        ">",
        RVOL_MIN
    )


    print(
        "=" * 70
    )


    # =====================================================
    # STEP 1 DAILY
    # =====================================================

    daily_df = get_daily_data()


    if daily_df.empty:

        message = create_no_alert_message(

            now,

            0,

            0,

            0,

            0

        )


        send_telegram(
            message
        )


        return


    daily_buy_df, daily_sell_df = (
        process_daily(
            daily_df
        )
    )


    daily_buy_symbols = set(

        daily_buy_df[
            "Symbol"
        ].tolist()

    )


    daily_sell_symbols = set(

        daily_sell_df[
            "Symbol"
        ].tolist()

    )


    # =====================================================
    # STEP 2 15 MIN
    # =====================================================

    min15_df = get_15min_data()


    if min15_df.empty:

        message = create_no_alert_message(

            now,

            len(daily_buy_df),

            len(daily_sell_df),

            0,

            0

        )


        send_telegram(
            message
        )


        return


    (
        intraday_buy_df,
        intraday_sell_df
    ) = process_15min(

        min15_df,

        daily_buy_symbols,

        daily_sell_symbols

    )


    # =====================================================
    # COMBINED
    # =====================================================

    intraday_frames = []


    if not intraday_buy_df.empty:

        intraday_frames.append(
            intraday_buy_df
        )


    if not intraday_sell_df.empty:

        intraday_frames.append(
            intraday_sell_df
        )


    if intraday_frames:

        intraday_df = pd.concat(

            intraday_frames,

            ignore_index=True

        )

    else:

        intraday_df = pd.DataFrame()


    # =====================================================
    # IMPORTANT COLUMNS
    # =====================================================

    rsi_col = find_column(

        intraday_df,

        ["rsi"]

    )


    rvol_col = find_column(

        intraday_df,

        ["relative", "volume"]

    )


    price_col = find_column(

        intraday_df,

        ["price"]

    )


    print()
    print(
        "RSI column:",
        rsi_col
    )


    print(
        "RVOL column:",
        rvol_col
    )


    print(
        "Price column:",
        price_col
    )


    # =====================================================
    # COOLDOWN
    # =====================================================

    sent = load_sent()


    new_alerts = apply_cooldown(

        intraday_df,

        sent,

        now

    )


    print()
    print(
        "Daily BUY:",
        len(daily_buy_df)
    )


    print(
        "Daily SELL:",
        len(daily_sell_df)
    )


    print(
        "15m Strong BUY:",
        len(intraday_buy_df)
    )


    print(
        "15m Strong SELL:",
        len(intraday_sell_df)
    )


    print(
        "New alerts after cooldown:",
        len(new_alerts)
    )


    # =====================================================
    # NO NEW ALERT
    # =====================================================

    if not new_alerts:

        message = create_no_alert_message(

            now,

            len(daily_buy_df),

            len(daily_sell_df),

            len(intraday_buy_df),

            len(intraday_sell_df)

        )


        print()
        print(
            "Telegram status message:"
        )


        print(
            message
        )


        telegram_success = send_telegram(

            message

        )


        if telegram_success:

            print(
                "Telegram status alert sent."
            )

        else:

            print(
                "Telegram status alert failed."
            )


        return


    # =====================================================
    # SEPARATE BUY / SELL
    # =====================================================

    buy_alerts = []


    sell_alerts = []


    for row in new_alerts:

        signal = str(

            row.get(
                "Signal",
                ""
            )

        ).upper()


        if signal == "STRONG BUY":

            buy_alerts.append(
                row
            )


        elif signal == "STRONG SELL":

            sell_alerts.append(
                row
            )


    # =====================================================
    # TELEGRAM MESSAGE
    # =====================================================

    msg = create_alert_message(

        now,

        buy_alerts,

        sell_alerts,

        len(daily_buy_df),

        len(daily_sell_df),

        len(intraday_buy_df),

        len(intraday_sell_df),

        rsi_col,

        rvol_col,

        price_col

    )


    print()
    print(
        "================================================"
    )


    print(
        "TELEGRAM MESSAGE PREVIEW"
    )


    print(
        "================================================"
    )


    print(
        msg
    )


    print(
        "================================================"
    )


    # =====================================================
    # SEND
    # =====================================================

    telegram_success = send_telegram(
        msg
    )


    # =====================================================
    # SAVE COOLDOWN
    # ONLY AFTER TELEGRAM SUCCESS
    # =====================================================

    if telegram_success:

        for row in new_alerts:

            symbol = clean_symbol(
                row["Symbol"]
            )


            signal = str(

                row.get(
                    "Signal",
                    ""
                )

            ).upper()


            alert_key = (
                f"{symbol}_{signal}"
            )


            sent[alert_key] = (
                now.isoformat()
            )


        save_sent(
            sent
        )


        print()
        print(
            "Cooldown state saved."
        )


    else:

        print()
        print(
            "Telegram failed."
        )


        print(
            "sent_alerts.json "
            "was NOT updated."
        )


    # =====================================================
    # FINISH
    # =====================================================

    print()
    print(
        "=" * 70
    )


    print(
        "FINISHED"
    )


    print(
        "Daily BUY:",
        len(daily_buy_df)
    )


    print(
        "Daily SELL:",
        len(daily_sell_df)
    )


    print(
        "15m BUY:",
        len(intraday_buy_df)
    )


    print(
        "15m SELL:",
        len(intraday_sell_df)
    )


    print(
        "New alerts:",
        len(new_alerts)
    )


    print(
        "=" * 70
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as e:

        print()
        print(
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        )

        print(
            "SCANNER FAILED"
        )

        print(
            "ERROR:",
            repr(e)
        )

        print(
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        )

        raise
