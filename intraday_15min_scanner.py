# ===============================================================
# 15-min Intraday Setup Scanner with Previous Day High/Low + VWAP
# ===============================================================

import os
import sys
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, time
import pytz

# -------------------------------
# 1. Pre-filtered stocks
# -------------------------------
STOCKS = [
    "HINDZINC.NS", "HINDCOPPER.NS", "NATIONALUM.NS", "NMDC.NS",
    "LAURUSLABS.NS", "AARTIPHARM.NS", "BIOCON.NS", "SAILIFE.NS", "GRANULES.NS", 
	"BALUFORGE.NS", "TDPOWERSYS.NS", "IGL.NS", "BORORENEW.NS"
]

TIMEFRAME = '15m'
LOOKBACK_DAYS = 60

# -------------------------------
# 2. Market hours check
# -------------------------------
ist = pytz.timezone('Asia/Kolkata')
now = datetime.now(ist).time()
market_open = time(9, 15)
market_close = time(15, 30)

# Detect manual run via workflow_dispatch
MANUAL_RUN = os.environ.get("GITHUB_EVENT_NAME", "") == "workflow_dispatch"

if not (market_open <= now <= market_close) and not MANUAL_RUN:
    print("Market closed. Exiting script.")
    sys.exit()

# -------------------------------
# 3. Telegram setup
# -------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Telegram token or chat ID not set!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        r = requests.post(url, json=payload, timeout=10)
        print("Telegram response:", r.status_code, r.text)
    except Exception as e:
        print("Telegram error:", repr(e))

# -------------------------------
# 4. Scan stocks
# -------------------------------
results = []

for symbol in STOCKS:
    try:
        data = yf.download(symbol, period=f'{LOOKBACK_DAYS}d', interval=TIMEFRAME, auto_adjust=True)
        if data.empty or len(data) < 2:
            print(f"Skipping {symbol}: insufficient data")
            continue

        # Current price info
        last_candle = data.iloc[-1]
        last_price = round(float(last_candle['Close']), 2)

        # Previous day high/low
        prev_day = data.iloc[-2]
        prev_high = float(prev_day['High'])
        prev_low = float(prev_day['Low'])

        # %Position relative to previous day
        last_position = ((last_price - prev_low) / (prev_high - prev_low)) * 100

        # VWAP calculation safely
        day_start = len(data) - 1 - ((len(data) - 1) % 26)  # approx 26 candles/day
        day_data = data.iloc[day_start:]
        typical_price = (day_data['High'] + day_data['Low'] + day_data['Close']) / 3

        if len(day_data) == 1:
            vwap = float(typical_price.iloc[0])
        else:
            vwap_calc = (typical_price * day_data['Volume']).sum() / day_data['Volume'].sum()
            vwap = float(vwap_calc.iloc[0]) if isinstance(vwap_calc, pd.Series) else float(vwap_calc)

        # VWAP signal
        vwap_signal = 'Above VWAP' if last_price > vwap else 'Below VWAP'

        # Current setup
        if last_position >= 85 and last_price > vwap:
            current_setup = 'Bullish'
        elif last_position <= 15 and last_price < vwap:
            current_setup = 'Bearish'
        else:
            current_setup = 'Neutral'

        results.append({
            'Stock': symbol,
            'Current Price': last_price,
            '%Position': round(last_position, 2),
            'VWAP Signal': vwap_signal,
            'Current Setup': current_setup
        })
    except Exception as e:
        print(f"{symbol} error:", repr(e))
        continue

# -------------------------------
# 5. Prepare Telegram message
# -------------------------------
if not results:
    telegram_message = "⚠️ No stocks found in this scan."
else:
    lines = []
    for row in results:
        lines.append(f"{row['Stock']}")
        lines.append(f"Current Price: {row['Current Price']}")
        lines.append(f"%Position: {row['%Position']}")
        lines.append(f"VWAP Signal: {row['VWAP Signal']}")
        lines.append(f"Current Setup: {row['Current Setup']}")
        lines.append("-" * 30)

    # Summary
    summary = pd.DataFrame(results)['Current Setup'].value_counts()
    lines.append("\n=== Summary ===")
    for k, v in summary.items():
        lines.append(f"{k}: {v} stock(s)")

    telegram_message = "\n".join(lines)

# -------------------------------
# 6. Send to Telegram
# -------------------------------
send_telegram(telegram_message)
