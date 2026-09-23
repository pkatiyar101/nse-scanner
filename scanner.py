import os
import json
import requests
from datetime import datetime, timedelta
from tvscreener import StockScreener, StockField, Market
import pandas as pd

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SENT_FILE = "sent_alerts.json"
COOLDOWN_MINUTES = 60

def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram config missing")
        print(msg)
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        print(f"Telegram response: {r.status_code}")
    except Exception as e:
        print(f"Telegram error: {e}")

def load_sent():
    if os.path.exists(SENT_FILE):
        try:
            with open(SENT_FILE) as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_sent(data):
    with open(SENT_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_signal(val):
    if pd.isna(val): return "NEUTRAL"
    if val >= 0.5: return "STRONG BUY"
    if val >= 0.1: return "BUY"
    if val <= -0.5: return "STRONG SELL"
    if val <= -0.1: return "SELL"
    return "NEUTRAL"

print(f"🔍 {datetime.now().strftime('%H:%M:%S')} — स्कैन शुरू...")

ss = StockScreener()
ss.set_markets(Market.INDIA)
ss.select(StockField.NAME, StockField.PRICE,
          StockField.HULLMA20, StockField.SIMPLE_MOVING_AVERAGE_50,
          StockField.RECOMMEND_ALL_15)
ss.where(StockField.HULLMA20 > StockField.SIMPLE_MOVING_AVERAGE_50)
ss.set_range(0, 500)
df = ss.get()

if df.empty:
    print("❌ कोई स्टॉक नहीं मिला")
    exit()

df['Symbol'] = df['Symbol'].str.split(':').str[-1]
df = df.drop_duplicates(subset=['Symbol'], keep='first')

rating_col = next((c for c in df.columns if 'Recommend' in c and '15' in c), None)
if not rating_col:
    print(f"⚠️ रेटिंग कॉलम नहीं मिला। कॉलम: {df.columns.tolist()}")
    exit()

df['Signal'] = df[rating_col].apply(get_signal)
strong_df = df[df[rating_col].abs() >= 0.5].copy()
print(f"✅ Strong Buy/Sell: {len(strong_df)}")

strong_symbols = strong_df['Symbol'].tolist()
intraday_df = pd.DataFrame()

if strong_symbols:
    ss2 = StockScreener()
    ss2.set_markets(Market.INDIA)
    ss2.select(StockField.NAME, StockField.PRICE, StockField.CHANGE_PERCENT,
               StockField.VOLUME, StockField.RELATIVE_VOLUME,
               StockField.RELATIVE_STRENGTH_INDEX_14,
               StockField.HULLMA20, StockField.SIMPLE_MOVING_AVERAGE_50,
               StockField.RECOMMEND_ALL_15)
    ss2.where(StockField.HULLMA20 > StockField.SIMPLE_MOVING_AVERAGE_50)
    ss2.where(StockField.RELATIVE_STRENGTH_INDEX_14 > 40)
    ss2.where(StockField.RELATIVE_STRENGTH_INDEX_14 < 70)
    ss2.where(StockField.RELATIVE_VOLUME > 1)
    ss2.set_range(0, 500)
    temp = ss2.get()

    if not temp.empty:
        temp['Symbol'] = temp['Symbol'].str.split(':').str[-1]
        temp = temp.drop_duplicates(subset=['Symbol'], keep='first')
        intraday_df = temp[temp['Symbol'].isin(strong_symbols)].copy()
        if rating_col in intraday_df.columns:
            intraday_df['Signal'] = intraday_df[rating_col].apply(get_signal)

print(f"✅ Intraday योग्य: {len(intraday_df)}")

sent = load_sent()
now = datetime.now()
new_alerts = []

for _, row in intraday_df.iterrows():
    sym = row['Symbol']
    last_sent = sent.get(sym)
    if last_sent:
        try:
            last_time = datetime.fromisoformat(last_sent)
            if now - last_time < timedelta(minutes=COOLDOWN_MINUTES):
                continue
        except:
            pass
    new_alerts.append(row)
    sent[sym] = now.isoformat()

save_sent(sent)

if not new_alerts:
    print("✅ कोई नया अलर्ट नहीं")
    exit()

msg = f"📊 <b>NSE स्कैन</b> ({now.strftime('%d-%b %H:%M')})\n\n"
msg += f"🔥 Strong Buy/Sell: <b>{len(strong_df)}</b>\n"
msg += f"🎯 Intraday योग्य: <b>{len(intraday_df)}</b>\n\n"
msg += f"🆕 <b>नए अलर्ट ({len(new_alerts)}):</b>\n"

for row in new_alerts:
    rsi = row.get('Relative Strength Index (14)', 'N/A')
    if isinstance(rsi, float):
        rsi = f"{rsi:.1f}"
    symbol = row['Symbol']
    tv_link = f"https://www.tradingview.com/chart/?symbol=NSE:{symbol}"
    msg += f'• <a href="{tv_link}"><b>{symbol}</b></a> — {row.get("Signal","N/A")} | RSI: {rsi}\n'

send_telegram(msg)
print(f"✅ {len(new_alerts)} अलर्ट भेजे गए")
