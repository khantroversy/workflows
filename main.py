!pip install yfinance pandas requests pytz --quiet

import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime
import pytz

# ===== CONFIG =====
PORTFOLIO = [
    "HINDZINC.NS", "HINDCOPPER.NS", "NATIONALUM.NS", "NMDC.NS",
    "LAURUSLABS.NS", "SYNGENE.NS", "RVNL.NS", "CONCOR.NS", "CCL.NS"
]
TELEGRAM_TOKEN = "8086513469:AAG69-SyQuF4VV1SCQVgX01WNcGIL7nBoDY"
CHAT_ID = "1063530236"

# ===== TELEGRAM FUNCTION =====
def send_telegram(message: str):
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
def run(debug=False):
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
    if debug:
        print("Done. Hits:", hits)

# ===== SCHEDULER (IST) =====
IST = pytz.timezone("Asia/Kolkata")
IST_HOUR = 21  # 2 PM IST
IST_MINUTE = 28

print(f"Scheduler started... will run daily at {IST_HOUR:02d}:{IST_MINUTE:02d} IST")

while True:
    now_ist = datetime.now(IST)
    if now_ist.hour == IST_HOUR and now_ist.minute == IST_MINUTE:
        run(debug=True)
        time.sleep(61)  # avoid multiple runs in same minute
    time.sleep(1)


#final code to deploy with scheduler
