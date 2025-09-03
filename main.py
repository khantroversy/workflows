import os
import yfinance as yf
import pandas as pd
import requests

# ===== CONFIG =====
PORTFOLIO = [
    "HINDZINC.NS", "HINDCOPPER.NS", "NATIONALUM.NS", "NMDC.NS",
    "LAURUSLABS.NS", "SYNGENE.NS", "RVNL.NS", "CONCOR.NS", "CCL.NS"
]

# Read Telegram token and chat ID from GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("8086513469:AAG69-SyQuF4VV1SCQVgX01WNcGIL7nBoDY")
CHAT_ID = os.environ.get("1063530236")

# ===== TELEGRAM FUNCTION =====
def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Telegram token or chat ID not set!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram error:", repr(e))

# ===== VOLUME CHECK FUNCTION =====
def check_volume_higher(symbol: str):
    try:
        df = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=False)
        if df is None or df.empty or len(df) < 2:
            return None
        yesterday_vol = int(df["Volume"].iloc[-2])
        today_vol = int(df["Volume"].iloc[-1])
        return symbol if today_vol > yesterday_vol else None
    except Exception as e:
        print(f"{symbol} error:", repr(e))
        return None

# ===== MAIN FUNCTION =====
def run():
    hits = []
    for s in PORTFOLIO:
        hit = check_volume_higher(s)
        if hit:
            hits.append(hit)
    if hits:
        msg = "🔔 Volume higher than yesterday:\n" + "\n".join(hits)
        send_telegram(msg)
    else:
        send_telegram("No stock has higher volume than yesterday.")
    print("Done. Hits:", hits)

# Run the bot
if __name__ == "__main__":
    run()
