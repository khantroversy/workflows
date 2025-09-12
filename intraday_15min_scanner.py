import os
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, time
import pytz
import sys

# ==========================
# MANUAL TEST CONFIG
# ==========================
# Set MANUAL_TEST=True as environment variable to bypass market hours (manual run)
MANUAL_TEST = os.environ.get("MANUAL_TEST", "False") == "false"

# ==========================
# MARKET HOURS CHECK
# ==========================
ist = pytz.timezone('Asia/Kolkata')
now = datetime.now(ist).time()
market_open = time(9, 15)
market_close = time(15, 30)

if not (market_open <= now <= market_close) and not MANUAL_TEST:
    print("Market closed. Exiting script.")
    sys.exit()
elif MANUAL_TEST:
    print("🚀 Manual test mode active: Running outside market hours")

# ==========================
# CONFIG
# ==========================
STOCKS = [
    "HINDZINC.NS", "HINDCOPPER.NS", "NATIONALUM.NS", "NMDC.NS",
    "LAURUSLABS.NS", "CCL.NS", "ENGINERSIN.NS",
    "BIOCON.NS", "BALUFORGE.NS", "AARTIPHARM.NS"
]

TIMEFRAME = '15m'
LOOKBACK_DAYS = 60  # Yahoo allows max 60 days for 15-min interval

# Telegram secrets from GitHub Actions
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# ==========================
# TELEGRAM FUNCTION
# ==========================
def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️ Telegram token or chat ID not set. Skipping message.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        r = requests.post(url, data=payload, timeout=10)
        print("Telegram response:", r.status_code, r.text)
    except Exception as e:
        print("Telegram error:", repr(e))

# ==========================
# SCANNER FUNCTION
# ==========================
def scan_stocks():
    results = []

    for symbol in STOCKS:
        data = yf.download(symbol, period=f'{LOOKBACK_DAYS}d', interval=TIMEFRAME, auto_adjust=True)
        if data.empty:
            print(f"Skipping {symbol}: no 15-min data available")
            continue

        last_candle = data.iloc[-1]
        last_price = last_candle['Close']
        last_price = round(last_price, 2)

        prev_day = data.iloc[-2]
        prev_high = prev_day['High']
        prev_low  = prev_day['Low']

        last_position = ((last_price - prev_low) / (prev_high - prev_low)) * 100

        # VWAP calculation for current day
        day_start = len(data) - 1 - ((len(data) - 1) % 26)  # approx 26 candles per trading day
        day_data = data.iloc[day_start:]
        typical_price = (day_data['High'] + day_data['Low'] + day_data['Close']) / 3
        vwap = (typical_price * day_data['Volume']).sum() / day_data['Volume'].sum()

        vwap_signal = 'Above VWAP' if last_price > vwap else 'Below VWAP'

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

    return results

# ==========================
# MAIN FUNCTION
# ==========================
def run():
    df_results = pd.DataFrame(scan_stocks())
    print("=== Individual Stock Setup Table ===")
    print(df_results)

    if df_results.empty:
        print("No stocks found.")
        return

    # Prepare Telegram message
    message_lines = []
    for _, row in df_results.iterrows():
        message_lines.append(f"{row['Stock']}")
        message_lines.append(f"Current Price: {row['Current Price']}")
        message_lines.append(f"%Position: {row['%Position']}")
        message_lines.append(f"VWAP Signal: {row['VWAP Signal']}")
        message_lines.append(f"Current Setup: {row['Current Setup']}")
        message_lines.append("-"*30)

    telegram_message = "\n".join(message_lines)
    send_telegram(telegram_message)

if __name__ == "__main__":
    run()
