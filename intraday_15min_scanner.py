import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime, time
import pytz
import sys

# ===== MARKET HOURS CHECK =====
ist = pytz.timezone('Asia/Kolkata')
now = datetime.now(ist).time()
market_open = time(9, 15)
market_close = time(15, 30)
if not (market_open <= now <= market_close):
    print("Market closed. Exiting script.")
    sys.exit()

# ===== CONFIG =====
STOCKS = [
    "HINDZINC.NS", "HINDCOPPER.NS", "NATIONALUM.NS", "NMDC.NS",
    "LAURUSLABS.NS", "CCL.NS", "ENGINERSIN.NS",
    "BIOCON.NS", "BALUFORGE.NS", "AARTIPHARM.NS"
]

TIMEFRAME = '15m'
LOOKBACK_DAYS = 60
FOLLOW_THROUGH_CANDLES = 4

# Telegram secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# ===== TELEGRAM FUNCTION =====
def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️ Telegram token or chat ID not set. Skipping message.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        r = requests.post(url, json=payload, timeout=10)
        print("Telegram response:", r.status_code, r.text)
    except Exception as e:
        print("Telegram error:", repr(e))

# ===== SCANNER FUNCTION =====
def scan_stocks():
    results = []

    for symbol in STOCKS:
        data = yf.download(symbol, period=f'{LOOKBACK_DAYS}d', interval=TIMEFRAME, auto_adjust=True)
        if data.empty:
            print(f"Skipping {symbol}: no 15-min data available")
            continue

        success_count = 0
        total_setups = 0

        for i in range(1, len(data) - FOLLOW_THROUGH_CANDLES):
            prev_day = data.iloc[i - 1]
            current = data.iloc[i]

            prev_high = prev_day['High']
            prev_low = prev_day['Low']
            current_price = current['Close']

            if prev_high == prev_low:
                continue

            position_pct = ((current_price - prev_low) / (prev_high - prev_low)) * 100

            # VWAP calculation
            day_start = i - (i % 26)
            day_data = data.iloc[day_start:i + 1]
            typical_price = (day_data['High'] + day_data['Low'] + day_data['Close']) / 3
            vwap = (typical_price * day_data['Volume']).sum() / day_data['Volume'].sum()

            future_slice = data.iloc[i + 1:i + 1 + FOLLOW_THROUGH_CANDLES]
            future_high = future_slice['High'].max() if not future_slice.empty else current_price
            future_low  = future_slice['Low'].min()  if not future_slice.empty else current_price

            if position_pct >= 85 and current_price > vwap:
                total_setups += 1
                if future_high > current_price:
                    success_count += 1
            elif position_pct <= 15 and current_price < vwap:
                total_setups += 1
                if future_low < current_price:
                    success_count += 1

        est_prob = round((success_count / total_setups * 100), 2) if total_setups > 0 else 0

        last_candle = data.iloc[-1]
        last_price = last_candle['Close']
        prev_day = data.iloc[-2]
        prev_high = prev_day['High']
        prev_low  = prev_day['Low']

        last_position = ((last_price - prev_low) / (prev_high - prev_low)) * 100
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
            'Current Setup': current_setup,
            'Historical Est. Prob (%)': est_prob
        })

    return results

# ===== MAIN FUNCTION =====
def run():
    df_results = pd.DataFrame(scan_stocks())
    if not df_results.empty:
        df_results = df_results.sort_values(by='Historical Est. Prob (%)', ascending=False).reset_index(drop=True)

    print("=== Individual Stock Setup Table ===")
    print(df_results)

    # Telegram
    message_lines = []
    for _, row in df_results.iterrows():
        message_lines.append(f"{row['Stock']}")
        message_lines.append(f"Current Price: {row['Current Price']}")
        message_lines.append(f"%Position: {row['%Position']}")
        message_lines.append(f"VWAP Signal: {row['VWAP Signal']}")
        message_lines.append(f"Current Setup: {row['Current Setup']}")
        message_lines.append(f"Historical Est. Prob (%): {row['Historical Est. Prob (%)']}")
        message_lines.append("-"*30)

    telegram_message = "\n".join(message_lines)
    send_telegram(telegram_message)

if __name__ == "__main__":
    run()
