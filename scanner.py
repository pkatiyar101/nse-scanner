print("===== NSE SCANNER VERSION 2026-09-25-V6.2 =====")
print("===== DAILY + 15M HULL/SMA + RSI + RVOL + TELEGRAM =====")

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

# Scanner cooldown is independent of GitHub Actions schedule.
COOLDOWN_MINUTES = 5

# 15-minute entry conditions
RSI_MIN = 40
RSI_MAX = 70
RVOL_MIN = 1.0

# Fetch enough Indian stock rows so the daily universe is not
# artificially limited to the first 500 rows.
PAGE_SIZE = 2000

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
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, data=payload, timeout=20)

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
# SENT ALERT STATE
# =========================================================

def load_sent():
    if not os.path.exists(SENT_FILE):
        return {}

    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, dict) else {}

    except Exception as e:
        print("Error reading sent file:", e)
        return {}


def save_sent(data):
    try:
        with open(SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return True

    except Exception as e:
        print("Error saving sent file:", e)
        return False


# =========================================================
# HELPERS
# =========================================================

def clean_symbol(symbol):
    if pd.isna(symbol):
        return ""

    symbol = str(symbol).strip().upper()

    if ":" in symbol:
        symbol = symbol.split(":")[-1]

    return symbol


def tradingview_link(symbol):
    symbol = clean_symbol(symbol)
    encoded_symbol = quote(f"NSE:{symbol}", safe="")
    return f"https://www.tradingview.com/chart/?symbol={encoded_symbol}"


def numeric(series):
    return pd.to_numeric(series, errors="coerce")


def find_column(df, exact_names=(), contains_all=()):
    # 1) Exact match first.
    for name in exact_names:
        if name in df.columns:
            return name

    # 2) Normalized text match. This handles TradingView names such as:
    #    "Simple Moving Average (50) (15)" and spacing/punctuation changes.
    def norm(value):
        return "".join(ch.lower() for ch in str(value) if ch.isalnum())

    normalized = {norm(col): col for col in df.columns}

    for name in exact_names:
        n = norm(name)
        if n in normalized:
            return normalized[n]

    wanted = [norm(x) for x in contains_all if norm(x)]

    for col in df.columns:
        text = norm(col)
        if all(x in text for x in wanted):
            return col

    return None


def print_columns(title, df):
    print()
    print(f"--- {title} columns ---")
    print(df.columns.tolist())


def get_signal(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "NEUTRAL"

    if pd.isna(value):
        return "NEUTRAL"

    if value >= 0.5:
        return "STRONG BUY"

    if value <= -0.5:
        return "STRONG SELL"

    if value >= 0.1:
        return "BUY"

    if value <= -0.1:
        return "SELL"

    return "NEUTRAL"


def get_float(row, column, default=None):
    if not column or column not in row.index:
        return default

    value = row[column]

    if pd.isna(value):
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# =========================================================
# DAILY SCAN
# =========================================================
# STEP 1:
# BUY  = Daily HULLMA20 > Daily SMA50
# SELL = Daily HULLMA20 < Daily SMA50
#
# IMPORTANT:
# We intentionally compare HULL and SMA in pandas. This avoids
# depending on a library/version-specific field-to-field filter.
# =========================================================

def get_daily_data():
    ss = StockScreener()
    ss.set_markets(Market.INDIA)

    ss.select(
        StockField.NAME,
        StockField.PRICE,
        StockField.HULLMA20,
        StockField.SIMPLE_MOVING_AVERAGE_50,
    )

    ss.set_range(0, PAGE_SIZE)

    df = ss.get()

    if df.empty:
        return df, set(), set()

    print_columns("DAILY", df)

    if "Symbol" not in df.columns:
        raise RuntimeError(
            f"Daily result does not contain Symbol. Columns: {df.columns.tolist()}"
        )

    df["Symbol"] = df["Symbol"].apply(clean_symbol)
    df = df[df["Symbol"] != ""].copy()
    df = df.drop_duplicates("Symbol", keep="first")

    hull_col = find_column(
        df,
        exact_names=("HULLMA20", "Hull MA 20"),
        contains_all=("hull", "20"),
    )

    sma_col = find_column(
        df,
        exact_names=("SMA50", "Simple Moving Average (50)"),
        contains_all=("simple", "moving", "average", "50"),
    )

    if not hull_col or not sma_col:
        raise RuntimeError(
            "Daily HULLMA20/SMA50 columns not found. "
            f"Columns: {df.columns.tolist()}"
        )

    df["_HULL_D"] = numeric(df[hull_col])
    df["_SMA_D"] = numeric(df[sma_col])

    df = df.dropna(subset=["_HULL_D", "_SMA_D"]).copy()

    buy_df = df[df["_HULL_D"] > df["_SMA_D"]].copy()
    sell_df = df[df["_HULL_D"] < df["_SMA_D"]].copy()

    buy_symbols = set(buy_df["Symbol"])
    sell_symbols = set(sell_df["Symbol"])

    print("Daily BUY candidates :", len(buy_df))
    print("Daily SELL candidates:", len(sell_df))

    return df, buy_symbols, sell_symbols


# =========================================================
# 15-MINUTE SCAN
# =========================================================
# STEP 2:
# BUY:
#   15M HULLMA20 > 15M SMA50
#   RSI 40..70
#   RVOL > 1
#   Recommend All|15 >= 0.5
#
# SELL:
#   15M HULLMA20 < 15M SMA50
#   RSI 40..70
#   RVOL > 1
#   Recommend All|15 <= -0.5
#
# All technical indicators below are explicitly 15-minute.
# =========================================================

def get_15min_data():
    hull15 = StockField.HULLMA20.with_interval("15")
    sma15 = StockField.SIMPLE_MOVING_AVERAGE_50.with_interval("15")
    rsi15 = StockField.RELATIVE_STRENGTH_INDEX_14.with_interval("15")
    rvol15 = StockField.RELATIVE_VOLUME.with_interval("15")

    ss = StockScreener()
    ss.set_markets(Market.INDIA)

    ss.select(
        StockField.NAME,
        StockField.PRICE,
        StockField.CHANGE_PERCENT,
        StockField.VOLUME,
        rvol15,
        rsi15,
        hull15,
        sma15,
        StockField.RECOMMEND_ALL_15,
    )

    # Server-side filters only on single-field conditions.
    # HULL vs SMA is compared safely in pandas below.
    ss.where(rsi15.between(RSI_MIN, RSI_MAX))
    ss.where(rvol15 > RVOL_MIN)

    ss.set_range(0, PAGE_SIZE)

    df = ss.get()

    if df.empty:
        return df

    print_columns("15-MINUTE", df)

    if "Symbol" not in df.columns:
        raise RuntimeError(
            f"15-minute result does not contain Symbol. "
            f"Columns: {df.columns.tolist()}"
        )

    df["Symbol"] = df["Symbol"].apply(clean_symbol)
    df = df[df["Symbol"] != ""].copy()
    df = df.drop_duplicates("Symbol", keep="first")

    hull_col = find_column(
        df,
        exact_names=("HULLMA20|15",),
        contains_all=("hull", "20", "15"),
    )

    sma_col = find_column(
        df,
        exact_names=("Simple Moving Average (50) (15)", "SMA50|15"),
        contains_all=("simple", "moving", "average", "50", "15"),
    )

    rsi_col = find_column(
        df,
        exact_names=("Relative Strength Index (14) (15)", "RSI14|15"),
        contains_all=("relative", "strength", "index", "14", "15"),
    )

    rvol_col = find_column(
        df,
        exact_names=("Relative Volume (15)", "Relative Volume|15"),
        contains_all=("relative", "volume", "15"),
    )

    rating_col = find_column(
        df,
        exact_names=("Recommend All|15",),
        contains_all=("recommend", "all", "15"),
    )

    if not hull_col or not sma_col or not rsi_col or not rvol_col:
        raise RuntimeError(
            "One or more 15-minute columns were not found.\n"
            f"HULL={hull_col}, SMA={sma_col}, RSI={rsi_col}, RVOL={rvol_col}\n"
            f"Columns: {df.columns.tolist()}"
        )

    if not rating_col:
        raise RuntimeError(
            "15-minute Recommend All column was not found.\n"
            f"Columns: {df.columns.tolist()}"
        )

    df["_HULL_15"] = numeric(df[hull_col])
    df["_SMA_15"] = numeric(df[sma_col])
    df["_RSI_15"] = numeric(df[rsi_col])
    df["_RVOL_15"] = numeric(df[rvol_col])
    df["_RATING_15"] = numeric(df[rating_col])

    df = df.dropna(
        subset=[
            "_HULL_15",
            "_SMA_15",
            "_RSI_15",
            "_RVOL_15",
            "_RATING_15",
        ]
    ).copy()

    df["Signal"] = "NEUTRAL"

    buy_mask = (
        (df["_HULL_15"] > df["_SMA_15"])
        & (df["_RSI_15"] >= RSI_MIN)
        & (df["_RSI_15"] <= RSI_MAX)
        & (df["_RVOL_15"] > RVOL_MIN)
        & (df["_RATING_15"] >= 0.5)
    )

    sell_mask = (
        (df["_HULL_15"] < df["_SMA_15"])
        & (df["_RSI_15"] >= RSI_MIN)
        & (df["_RSI_15"] <= RSI_MAX)
        & (df["_RVOL_15"] > RVOL_MIN)
        & (df["_RATING_15"] <= -0.5)
    )

    df.loc[buy_mask, "Signal"] = "STRONG BUY"
    df.loc[sell_mask, "Signal"] = "STRONG SELL"

    qualified = df[df["Signal"] != "NEUTRAL"].copy()

    print("15M Strong BUY :", int((qualified["Signal"] == "STRONG BUY").sum()))
    print("15M Strong SELL:", int((qualified["Signal"] == "STRONG SELL").sum()))

    return qualified


# =========================================================
# COOLDOWN
# =========================================================
# BUY and SELL have separate cooldown keys.
# Example:
#   RELIANCE_STRONG BUY
#   RELIANCE_STRONG SELL
# =========================================================

def apply_cooldown(df, sent, now):
    new_rows = []

    for _, row in df.iterrows():
        symbol = clean_symbol(row["Symbol"])
        signal = str(row.get("Signal", "NEUTRAL")).strip().upper()

        if not symbol or signal not in ("STRONG BUY", "STRONG SELL"):
            continue

        key = f"{symbol}_{signal.replace(' ', '_')}"
        last_sent = sent.get(key)

        if last_sent:
            try:
                last_time = datetime.fromisoformat(last_sent)

                if last_time.tzinfo is None:
                    last_time = last_time.replace(tzinfo=IST)

                elapsed = now - last_time

                if elapsed < timedelta(minutes=COOLDOWN_MINUTES):
                    print(
                        f"{symbol} {signal} skipped - "
                        f"cooldown {COOLDOWN_MINUTES} min"
                    )
                    continue

            except Exception as e:
                print("Cooldown parse error:", key, e)

        row = row.copy()
        row["_ALERT_KEY"] = key
        new_rows.append(row)

    return new_rows


# =========================================================
# TELEGRAM FORMATTING
# =========================================================

def format_stock_line(row):
    symbol = clean_symbol(row["Symbol"])
    signal = str(row.get("Signal", "N/A"))

    price = get_float(row, "Price", None)
    if price is None:
        price_text = "N/A"
    else:
        price_text = f"{price:.2f}"

    rsi = get_float(row, "_RSI_15", None)
    rsi_text = "N/A" if rsi is None else f"{rsi:.1f}"

    rvol = get_float(row, "_RVOL_15", None)
    rvol_text = "N/A" if rvol is None else f"{rvol:.2f}"

    rating = get_float(row, "_RATING_15", None)
    rating_text = "N/A" if rating is None else f"{rating:.2f}"

    safe_symbol = html.escape(symbol)
    safe_signal = html.escape(signal)
    tv_url = tradingview_link(symbol)

    return (
        f'• <a href="{tv_url}"><b>{safe_symbol}</b></a>'
        f" — {safe_signal}"
        f" | Price: {price_text}"
        f" | RSI: {rsi_text}"
        f" | RVOL: {rvol_text}"
        f" | Rec: {rating_text}\n"
    )


def build_status_message(
    now,
    daily_buy_count,
    daily_sell_count,
    qualified_buy_count,
    qualified_sell_count,
    new_buy_count,
    new_sell_count,
):
    total_qualified = qualified_buy_count + qualified_sell_count
    total_new = new_buy_count + new_sell_count

    return (
        f"📊 <b>NSE SCAN</b> "
        f"({now.strftime('%d-%b %H:%M')} IST)\n\n"
        f"📈 Daily BUY: <b>{daily_buy_count}</b>\n"
        f"📉 Daily SELL: <b>{daily_sell_count}</b>\n"
        f"🟢 15M Strong BUY: <b>{qualified_buy_count}</b>\n"
        f"🔴 15M Strong SELL: <b>{qualified_sell_count}</b>\n\n"
        f"🆕 New BUY alerts: <b>{new_buy_count}</b>\n"
        f"🆕 New SELL alerts: <b>{new_sell_count}</b>\n"
        f"📌 Total new alerts: <b>{total_new}</b>\n"
        f"⏱ Cooldown: <b>{COOLDOWN_MINUTES} min</b>"
    )


def build_alert_message(
    now,
    daily_buy_count,
    daily_sell_count,
    qualified_buy_count,
    qualified_sell_count,
    new_buy_rows,
    new_sell_rows,
):
    msg = (
        f"📊 <b>NSE SCAN</b> "
        f"({now.strftime('%d-%b %H:%M')} IST)\n\n"
        f"📈 Daily BUY: <b>{daily_buy_count}</b>\n"
        f"📉 Daily SELL: <b>{daily_sell_count}</b>\n"
        f"🟢 15M Strong BUY: <b>{qualified_buy_count}</b>\n"
        f"🔴 15M Strong SELL: <b>{qualified_sell_count}</b>\n\n"
    )

    if new_buy_rows:
        msg += f"🟢 <b>STRONG BUY ({len(new_buy_rows)})</b>\n"
        for row in new_buy_rows:
            msg += format_stock_line(row)
        msg += "\n"

    if new_sell_rows:
        msg += f"🔴 <b>STRONG SELL ({len(new_sell_rows)})</b>\n"
        for row in new_sell_rows:
            msg += format_stock_line(row)
        msg += "\n"

    msg += f"⏱ Cooldown: <b>{COOLDOWN_MINUTES} min</b>"

    return msg


# =========================================================
# MAIN
# =========================================================

def main():
    now = datetime.now(IST)

    print()
    print("=" * 70)
    print("NSE SCANNER V6")
    print(
        "UTC TIME:",
        datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M:%S"),
    )
    print(
        "IST TIME:",
        now.strftime("%d-%b-%Y %H:%M:%S"),
    )
    print("=" * 70)

    # -----------------------------------------------------
    # STEP 1: DAILY
    # -----------------------------------------------------

    try:
        daily_df, daily_buy_symbols, daily_sell_symbols = get_daily_data()
    except Exception as e:
        print("Daily scanner error:", e)
        raise

    if daily_df.empty or (
        not daily_buy_symbols and not daily_sell_symbols
    ):
        msg = (
            f"📊 <b>NSE SCAN</b> "
            f"({now.strftime('%d-%b %H:%M')} IST)\n\n"
            f"⚪ <b>NO DAILY CANDIDATES FOUND</b>\n\n"
            f"📈 Daily BUY: <b>0</b>\n"
            f"📉 Daily SELL: <b>0</b>\n"
            f"⏱ Cooldown: <b>{COOLDOWN_MINUTES} min</b>"
        )
        send_telegram(msg)
        print("No daily candidates. Scanner finished.")
        return

    # -----------------------------------------------------
    # STEP 2: 15 MINUTE
    # -----------------------------------------------------

    try:
        qualified_15m = get_15min_data()
    except Exception as e:
        print("15-minute scanner error:", e)
        raise

    if qualified_15m.empty:
        msg = build_status_message(
            now,
            len(daily_buy_symbols),
            len(daily_sell_symbols),
            0,
            0,
            0,
            0,
        )
        print("No 15-minute qualified stocks.")
        send_telegram(msg)
        return

    # -----------------------------------------------------
    # APPLY DAILY DIRECTION
    # -----------------------------------------------------

    qualified_15m["DailyDirection"] = qualified_15m["Symbol"].map(
        lambda s: (
            "BUY" if s in daily_buy_symbols
            else "SELL" if s in daily_sell_symbols
            else ""
        )
    )

    qualified_15m = qualified_15m[
        (
            (qualified_15m["Signal"] == "STRONG BUY")
            & (qualified_15m["DailyDirection"] == "BUY")
        )
        |
        (
            (qualified_15m["Signal"] == "STRONG SELL")
            & (qualified_15m["DailyDirection"] == "SELL")
        )
    ].copy()

    qualified_buy = qualified_15m[
        qualified_15m["Signal"] == "STRONG BUY"
    ].copy()

    qualified_sell = qualified_15m[
        qualified_15m["Signal"] == "STRONG SELL"
    ].copy()

    print("Final BUY:", len(qualified_buy))
    print("Final SELL:", len(qualified_sell))

    # -----------------------------------------------------
    # COOLDOWN
    # -----------------------------------------------------

    sent = load_sent()
    new_rows = apply_cooldown(
        qualified_15m,
        sent,
        now,
    )

    new_buy_rows = [
        row for row in new_rows
        if str(row.get("Signal", "")).upper() == "STRONG BUY"
    ]

    new_sell_rows = [
        row for row in new_rows
        if str(row.get("Signal", "")).upper() == "STRONG SELL"
    ]

    # -----------------------------------------------------
    # NO NEW ALERT
    # -----------------------------------------------------

    if not new_rows:
        status_msg = build_status_message(
            now,
            len(daily_buy_symbols),
            len(daily_sell_symbols),
            len(qualified_buy),
            len(qualified_sell),
            0,
            0,
        )

        print()
        print("Telegram status message:")
        print(status_msg)

        send_telegram(status_msg)
        return

    # -----------------------------------------------------
    # ALERT MESSAGE
    # -----------------------------------------------------

    msg = build_alert_message(
        now,
        len(daily_buy_symbols),
        len(daily_sell_symbols),
        len(qualified_buy),
        len(qualified_sell),
        new_buy_rows,
        new_sell_rows,
    )

    print()
    print("Telegram alert preview:")
    print(msg)

    telegram_success = send_telegram(msg)

    # -----------------------------------------------------
    # SAVE COOLDOWN ONLY AFTER TELEGRAM SUCCESS
    # -----------------------------------------------------

    if telegram_success:
        for row in new_rows:
            key = row["_ALERT_KEY"]
            sent[key] = now.isoformat()

        if save_sent(sent):
            print(f"{len(new_rows)} new alerts saved.")
        else:
            print("WARNING: Telegram sent, but sent_alerts.json save failed.")
    else:
        print("Telegram failed. sent_alerts.json was NOT updated.")

    # -----------------------------------------------------
    # FINISH
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("Finished IST:", now.strftime("%d-%b-%Y %H:%M:%S"))
    print("Daily BUY:", len(daily_buy_symbols))
    print("Daily SELL:", len(daily_sell_symbols))
    print("Final BUY:", len(qualified_buy))
    print("Final SELL:", len(qualified_sell))
    print("New BUY:", len(new_buy_rows))
    print("New SELL:", len(new_sell_rows))
    print("=" * 70)


if __name__ == "__main__":
    main()
