print("==============================================================")
print("===== NSE SCANNER VERSION 2026-09-25-BUY-SELL-DUAL-TF =====")
print("===== DAILY + 15 MIN + TELEGRAM + TRADINGVIEW =====")
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

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

SENT_FILE = "sent_alerts.json"

# Same stock can alert again after 5 minutes
COOLDOWN_MINUTES = 5

# RSI range for both Buy and Sell
RSI_MIN = 40
RSI_MAX = 70

# Relative Volume
RVOL_MIN = 1


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

        print("Telegram configuration missing")
        print(msg)

        return False


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
            e
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

            return json.load(f)


    except Exception as e:

        print(
            "Error reading sent file:",
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
            "Error saving sent file:",
            e
        )

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
        f"https://www.tradingview.com/chart/"
        f"?symbol={encoded_symbol}"
    )


# =========================================================
# FIND COLUMN
# =========================================================

def find_column(
    df,
    keywords
):

    for col in df.columns:

        col_text = str(
            col
        ).lower()


        if all(
            str(k).lower()
            in col_text
            for k in keywords
        ):

            return col


    return None


# =========================================================
# START
# =========================================================

now = datetime.now(
    IST
)


print()
print(
    "=" * 65
)

print(
    "NSE SCANNER"
)

print(
    "UTC TIME :",
    datetime.now(
        timezone.utc
    ).strftime(
        "%d-%b-%Y %H:%M:%S"
    )
)

print(
    "IST TIME :",
    now.strftime(
        "%d-%b-%Y %H:%M:%S"
    )
)

print(
    "COOLDOWN :",
    COOLDOWN_MINUTES,
    "minutes"
)

print(
    "RSI RANGE:",
    RSI_MIN,
    "-",
    RSI_MAX
)

print(
    "RVOL MIN :",
    RVOL_MIN
)

print(
    "=" * 65
)


# =========================================================
# =========================================================
# STEP 1A — DAILY BUY
# HULLMA20 > SMA50
# =========================================================
# =========================================================

print()
print(
    "========== STEP 1A : DAILY BUY =========="
)

daily_buy_df = pd.DataFrame()


try:

    ss_buy = StockScreener()

    ss_buy.set_markets(
        Market.INDIA
    )


    ss_buy.select(

        StockField.NAME,

        StockField.PRICE,

        StockField.HULLMA20,

        StockField.SIMPLE_MOVING_AVERAGE_50
    )


    ss_buy.where(

        StockField.HULLMA20
        >
        StockField.SIMPLE_MOVING_AVERAGE_50
    )


    ss_buy.set_range(
        0,
        500
    )


    daily_buy_df = ss_buy.get()


except Exception as e:

    print(
        "Daily BUY scanner error:",
        e
    )

    raise


if not daily_buy_df.empty:

    daily_buy_df["Symbol"] = (
        daily_buy_df["Symbol"]
        .apply(clean_symbol)
    )


    daily_buy_df = daily_buy_df[
        daily_buy_df["Symbol"] != ""
    ]


    daily_buy_df = daily_buy_df.drop_duplicates(
        subset=["Symbol"],
        keep="first"
    )


print(
    "Daily BUY candidates:",
    len(daily_buy_df)
)


# =========================================================
# STEP 1B — DAILY SELL
# HULLMA20 < SMA50
# =========================================================

print()
print(
    "========== STEP 1B : DAILY SELL =========="
)

daily_sell_df = pd.DataFrame()


try:

    ss_sell = StockScreener()

    ss_sell.set_markets(
        Market.INDIA
    )


    ss_sell.select(

        StockField.NAME,

        StockField.PRICE,

        StockField.HULLMA20,

        StockField.SIMPLE_MOVING_AVERAGE_50
    )


    ss_sell.where(

        StockField.HULLMA20
        <
        StockField.SIMPLE_MOVING_AVERAGE_50
    )


    ss_sell.set_range(
        0,
        500
    )


    daily_sell_df = ss_sell.get()


except Exception as e:

    print(
        "Daily SELL scanner error:",
        e
    )

    raise


if not daily_sell_df.empty:

    daily_sell_df["Symbol"] = (
        daily_sell_df["Symbol"]
        .apply(clean_symbol)
    )


    daily_sell_df = daily_sell_df[
        daily_sell_df["Symbol"] != ""
    ]


    daily_sell_df = daily_sell_df.drop_duplicates(
        subset=["Symbol"],
        keep="first"
    )


print(
    "Daily SELL candidates:",
    len(daily_sell_df)
)


# =========================================================
# DAILY SYMBOL LISTS
# =========================================================

daily_buy_symbols = set(
    daily_buy_df["Symbol"].tolist()
    if not daily_buy_df.empty
    else []
)


daily_sell_symbols = set(
    daily_sell_df["Symbol"].tolist()
    if not daily_sell_df.empty
    else []
)


# =========================================================
# =========================================================
# STEP 2A — 15 MIN BUY
# =========================================================

print()
print(
    "========== STEP 2A : 15 MIN BUY =========="
)


intraday_buy_df = pd.DataFrame()


if daily_buy_symbols:

    try:

        ss15_buy = StockScreener()

        ss15_buy.set_markets(
            Market.INDIA
        )


        # ---------------------------------------------
        # 15 MINUTE FIELDS
        # ---------------------------------------------

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


        RVOL_15 = (
            StockField.RELATIVE_VOLUME
            .with_interval("15")
        )


        # ---------------------------------------------
        # SELECT
        # ---------------------------------------------

        ss15_buy.select(

            StockField.NAME,

            StockField.PRICE,

            StockField.CHANGE_PERCENT,

            StockField.VOLUME,

            RVOL_15,

            RSI14_15,

            HULLMA20_15,

            SMA50_15,

            StockField.RECOMMEND_ALL_15
        )


        # ---------------------------------------------
        # 15 MIN BUY
        # HULLMA20 > SMA50
        # ---------------------------------------------

        ss15_buy.where(

            HULLMA20_15
            >
            SMA50_15
        )


        # ---------------------------------------------
        # RSI 40-70
        # ---------------------------------------------

        ss15_buy.where(

            RSI14_15 > RSI_MIN
        )


        ss15_buy.where(

            RSI14_15 < RSI_MAX
        )


        # ---------------------------------------------
        # RVOL > 1
        # ---------------------------------------------

        ss15_buy.where(

            RVOL_15 > RVOL_MIN
        )


        ss15_buy.set_range(
            0,
            500
        )


        temp_buy = ss15_buy.get()


        print(
            "15m BUY raw result:",
            len(temp_buy)
        )


        if not temp_buy.empty:

            temp_buy["Symbol"] = (
                temp_buy["Symbol"]
                .apply(clean_symbol)
            )


            temp_buy = temp_buy[
                temp_buy["Symbol"] != ""
            ]


            temp_buy = temp_buy.drop_duplicates(
                subset=["Symbol"],
                keep="first"
            )


            # Intersection with DAILY BUY
            intraday_buy_df = temp_buy[
                temp_buy["Symbol"].isin(
                    daily_buy_symbols
                )
            ].copy()


            # -----------------------------------------
            # RECOMMENDATION
            # -----------------------------------------

            buy_rating_col = next(

                (
                    c for c in intraday_buy_df.columns

                    if (
                        "recommend" in str(c).lower()
                        and "15" in str(c).lower()
                    )
                ),

                None
            )


            if buy_rating_col:

                intraday_buy_df["Signal"] = (
                    intraday_buy_df[
                        buy_rating_col
                    ].apply(get_signal)
                )


                # ONLY STRONG BUY
                intraday_buy_df = (
                    intraday_buy_df[
                        intraday_buy_df[
                            buy_rating_col
                        ] >= 0.5
                    ].copy()
                )


                print(
                    "BUY rating column:",
                    buy_rating_col
                )


    except Exception as e:

        print(
            "15 minute BUY scanner error:",
            e
        )

        raise


else:

    print(
        "No Daily BUY candidates."
    )


print(
    "15m BUY qualified:",
    len(intraday_buy_df)
)


# =========================================================
# =========================================================
# STEP 2B — 15 MIN SELL
# =========================================================

print()
print(
    "========== STEP 2B : 15 MIN SELL =========="
)


intraday_sell_df = pd.DataFrame()


if daily_sell_symbols:

    try:

        ss15_sell = StockScreener()

        ss15_sell.set_markets(
            Market.INDIA
        )


        # ---------------------------------------------
        # 15 MINUTE FIELDS
        # ---------------------------------------------

        HULLMA20_15_SELL = (
            StockField.HULLMA20
            .with_interval("15")
        )


        SMA50_15_SELL = (
            StockField.SIMPLE_MOVING_AVERAGE_50
            .with_interval("15")
        )


        RSI14_15_SELL = (
            StockField.RELATIVE_STRENGTH_INDEX_14
            .with_interval("15")
        )


        RVOL_15_SELL = (
            StockField.RELATIVE_VOLUME
            .with_interval("15")
        )


        # ---------------------------------------------
        # SELECT
        # ---------------------------------------------

        ss15_sell.select(

            StockField.NAME,

            StockField.PRICE,

            StockField.CHANGE_PERCENT,

            StockField.VOLUME,

            RVOL_15_SELL,

            RSI14_15_SELL,

            HULLMA20_15_SELL,

            SMA50_15_SELL,

            StockField.RECOMMEND_ALL_15
        )


        # ---------------------------------------------
        # 15 MIN SELL
        # HULLMA20 < SMA50
        # ---------------------------------------------

        ss15_sell.where(

            HULLMA20_15_SELL
            <
            SMA50_15_SELL
        )


        # ---------------------------------------------
        # RSI 40-70
        # ---------------------------------------------

        ss15_sell.where(

            RSI14_15_SELL > RSI_MIN
        )


        ss15_sell.where(

            RSI14_15_SELL < RSI_MAX
        )


        # ---------------------------------------------
        # RVOL > 1
        # ---------------------------------------------

        ss15_sell.where(

            RVOL_15_SELL > RVOL_MIN
        )


        ss15_sell.set_range(
            0,
            500
        )


        temp_sell = ss15_sell.get()


        print(
            "15m SELL raw result:",
            len(temp_sell)
        )


        if not temp_sell.empty:

            temp_sell["Symbol"] = (
                temp_sell["Symbol"]
                .apply(clean_symbol)
            )


            temp_sell = temp_sell[
                temp_sell["Symbol"] != ""
            ]


            temp_sell = temp_sell.drop_duplicates(
                subset=["Symbol"],
                keep="first"
            )


            # Intersection with DAILY SELL
            intraday_sell_df = temp_sell[
                temp_sell["Symbol"].isin(
                    daily_sell_symbols
                )
            ].copy()


            # -----------------------------------------
            # RECOMMENDATION
            # -----------------------------------------

            sell_rating_col = next(

                (
                    c for c in intraday_sell_df.columns

                    if (
                        "recommend" in str(c).lower()
                        and "15" in str(c).lower()
                    )
                ),

                None
            )


            if sell_rating_col:

                intraday_sell_df["Signal"] = (
                    intraday_sell_df[
                        sell_rating_col
                    ].apply(get_signal)
                )


                # ONLY STRONG SELL
                intraday_sell_df = (
                    intraday_sell_df[
                        intraday_sell_df[
                            sell_rating_col
                        ] <= -0.5
                    ].copy()
                )


                print(
                    "SELL rating column:",
                    sell_rating_col
                )


    except Exception as e:

        print(
            "15 minute SELL scanner error:",
            e
        )

        raise


else:

    print(
        "No Daily SELL candidates."
    )


print(
    "15m SELL qualified:",
    len(intraday_sell_df)
)


# =========================================================
# COMBINE BUY + SELL
# =========================================================

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


print()
print(
    "================================================"
)

print(
    "TOTAL 15m QUALIFIED:",
    len(intraday_df)
)

print(
    "================================================"
)


# =========================================================
# FIND IMPORTANT COLUMNS
# =========================================================

rsi_col = find_column(
    intraday_df,
    ["rsi"]
) if not intraday_df.empty else None


rvol_col = find_column(
    intraday_df,
    ["relative", "volume"]
) if not intraday_df.empty else None


price_col = find_column(
    intraday_df,
    ["price"]
) if not intraday_df.empty else None


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


# =========================================================
# COOLDOWN
# =========================================================

sent = load_sent()

now = datetime.now(
    IST
)


new_alerts = []


for _, row in intraday_df.iterrows():

    symbol = clean_symbol(
        row["Symbol"]
    )


    if not symbol:

        continue


    last_sent = sent.get(
        symbol
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
                    "skipped - cooldown"
                )

                continue


        except Exception as e:

            print(
                "Cooldown parse error:",
                symbol,
                e
            )


    new_alerts.append(
        row
    )


print()
print(
    "New alerts after cooldown:",
    len(new_alerts)
)


# =========================================================
# NO NEW ALERT
# =========================================================

if not new_alerts:

    print(
        "No new alerts"
    )


    message = (

        f"📊 <b>NSE SCAN</b> — "
        f"{now.strftime('%d-%b %H:%M')} IST\n\n"

        f"⚪ <b>NEW STOCKS NOT MATCH "
        f"AS PER CONDITION</b>\n\n"

        f"📈 Daily BUY candidates: "
        f"<b>{len(daily_buy_df)}</b>\n"

        f"📉 Daily SELL candidates: "
        f"<b>{len(daily_sell_df)}</b>\n"

        f"🔥 15m Strong BUY: "
        f"<b>{len(intraday_buy_df)}</b>\n"

        f"🎯 15m Strong SELL: "
        f"<b>{len(intraday_sell_df)}</b>\n"

        f"🆕 New Alerts: "
        f"<b>0</b>"
    )


    print()
    print(
        "Telegram status message:"
    )

    print(
        message
    )

    print()


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


    print()
    print(
        "Current IST:",
        now.strftime(
            "%d-%b-%Y %H:%M:%S"
        )
    )


    raise SystemExit


# =========================================================
# SEPARATE BUY / SELL ALERTS
# =========================================================

buy_alerts = []

sell_alerts = []


for row in new_alerts:

    signal = str(

        row.get(
            "Signal",
            "NEUTRAL"
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


# =========================================================
# TELEGRAM MESSAGE
# =========================================================

msg = (

    f"📊 <b>NSE SCAN</b> — "
    f"{now.strftime('%d-%b %H:%M')} IST\n\n"

)


# =========================================================
# STRONG BUY
# =========================================================

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


        try:

            rsi = f"{float(rsi):.1f}"

        except Exception:

            rsi = str(rsi)


        try:

            rvol = f"{float(rvol):.2f}"

        except Exception:

            rvol = str(rvol)


        try:

            price = f"₹{float(price):,.2f}"

        except Exception:

            price = f"₹{price}"


        tv_url = tradingview_link(
            symbol
        )


        safe_symbol = html.escape(
            symbol
        )


        msg += (

            f"• <b>{safe_symbol}</b>\n"

            f"  RSI: {rsi}\n"

            f"  RVOL: {rvol}\n"

            f"  Price: {price}\n"

            f'  📈 <a href="{tv_url}">'
            f"TradingView"
            f"</a>\n\n"

        )


else:

    msg += (
        "• No Strong Buy alerts\n\n"
    )


# =========================================================
# STRONG SELL
# =========================================================

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


        try:

            rsi = f"{float(rsi):.1f}"

        except Exception:

            rsi = str(rsi)


        try:

            rvol = f"{float(rvol):.2f}"

        except Exception:

            rvol = str(rvol)


        try:

            price = f"₹{float(price):,.2f}"

        except Exception:

            price = f"₹{price}"


        tv_url = tradingview_link(
            symbol
        )


        safe_symbol = html.escape(
            symbol
        )


        msg += (

            f"• <b>{safe_symbol}</b>\n"

            f"  RSI: {rsi}\n"

            f"  RVOL: {rvol}\n"

            f"  Price: {price}\n"

            f'  📉 <a href="{tv_url}">'
            f"TradingView"
            f"</a>\n\n"

        )


else:

    msg += (
        "• No Strong Sell alerts\n\n"
    )


# =========================================================
# SUMMARY
# =========================================================

msg += (

    f"📈 Daily BUY: "
    f"<b>{len(daily_buy_df)}</b>\n"

    f"📉 Daily SELL: "
    f"<b>{len(daily_sell_df)}</b>\n"

    f"🔥 15m Strong BUY: "
    f"<b>{len(intraday_buy_df)}</b>\n"

    f"🎯 15m Strong SELL: "
    f"<b>{len(intraday_sell_df)}</b>\n"

    f"🆕 New Alerts: "
    f"<b>{len(new_alerts)}</b>"

)


# =========================================================
# DEBUG
# =========================================================

print()
print(
    "Telegram message preview:"
)

print(
    msg
)

print()


# =========================================================
# SEND TELEGRAM
# =========================================================

telegram_success = send_telegram(
    msg
)


# =========================================================
# SAVE COOLDOWN AFTER SUCCESS
# =========================================================

if telegram_success:

    for row in new_alerts:

        symbol = clean_symbol(
            row["Symbol"]
        )


        sent[symbol] = (
            now.isoformat()
        )


    save_sent(
        sent
    )


    print(
        f"{len(new_alerts)} "
        f"alerts sent successfully"
    )


else:

    print(
        "Telegram send failed"
    )


    print(
        "sent_alerts.json "
        "was not updated"
    )


# =========================================================
# FINISH
# =========================================================

print()

print(
    "=" * 65
)

print(
    "Finished IST:",
    now.strftime(
        "%d-%b-%Y %H:%M:%S"
    )
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
    "=" * 65
)
