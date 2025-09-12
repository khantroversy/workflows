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
# 1. List of pre-filtered stocks
# -------------------------------
STOCKS = [
    "HINDZINC.NS", "HINDCOPPER.NS", "NATIONALUM.NS", "NMDC.NS",
    "LAURUSLABS.NS", "CCL.NS", "ENGINERSIN.NS", 
    "BIOCON.NS", "BALUFORGE.NS", "AARTIPHARM.NS"
]

TIMEFRAME = '15m'
LOOKBACK_DAYS = 60  # Yahoo allows max 60 days for 15-min interval

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
    data = yf.download(symbol, period=f'{LOOKBACK_DAYS}d', interval=TIMEFRAME, auto_adjust=True)
    if data.empty:
        print(f"Skipping {symbol}: no 15-min data available")
        continue

    # Current price info
    last_candle = data.iloc[-1]
    last_price = round(last_candle['Close'], 2)

    # Previous day high/low
    prev_day = data.iloc[-2]
    prev_high = prev_day['High']
    prev_low  = prev_day['Low']

    # %Position relative to previous day
    last_position = ((last_price - prev_low) / (prev_high - prev_low)) * 100

    # VWAP calculation
    day_start = len(data) - 1 - ((len(data) - 1) % 26)  # approx 26 candles per trading day
    day_data = data.iloc[day_start:]
    typical_price = (day_data['High'] + day_data['Low'] + day_data['Close']) / 3
    vwap_series = (typical_price * day_data['Volume']).sum() / day_data['Volume'].sum()
    # Force scalar safely
    vwap = float(vwap_series) if not isinstance(vwap_series, pd.Series) else float(vwap_series.iloc[0])

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
    telegram_message = "\n".join(lines)

# -------------------------------
# 6. Send to Telegram
# -------------------------------
send_telegram(telegram_message)
