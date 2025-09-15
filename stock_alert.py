import yfinance as yf
import pandas as pd
import requests
import os

# -------- Stock list --------
stocks = [
    "HINDZINC.NS", "HINDCOPPER.NS", "NATIONALUM.NS", "NMDC.NS",
    "LAURUSLABS.NS", "AARTIPHARM.NS", "BIOCON.NS", "SAILIFE.NS", "GRANULES.NS",
    "BALUFORGE.NS", "TDPOWERSYS.NS", "IGL.NS", "BORORENEW.NS"
]

lookback_days = 10
table_data = []

for stock in stocks:
    hist = yf.download(stock, period=f"{lookback_days}d", interval="1d", auto_adjust=True)
    if hist.empty:
        continue

    cmp = round(hist["Close"].iloc[-1].item(), 1)
    low_10 = round(hist["Low"].tail(10).min().item(), 1)
    max_vol_pos = hist["Volume"].values.argmax()
    high_vol_price = round(hist["Close"].iloc[max_vol_pos].item(), 1)
    yesterdays_low = round(hist["Low"].iloc[-2].item(), 1) if len(hist) > 1 else None
    todays_low = round(hist["Low"].iloc[-1].item(), 1)

    # Status vs HVZ
    tolerance = 0.01
    lower_bound = high_vol_price * (1 - tolerance)
    upper_bound = high_vol_price * (1 + tolerance)
    if cmp < lower_bound:
        status = "Below HVZ"
    elif cmp > upper_bound:
        status = "Above HVZ"
    else:
        status = "Near HVZ"

    # Perfect Confluence logic
    if status == "Near HVZ":
        if todays_low <= high_vol_price and (yesterdays_low is None or yesterdays_low <= high_vol_price):
            perfect_confluence = "Yes"
        else:
            perfect_confluence = "No"
    else:
        perfect_confluence = "No"

    table_data.append({
        "Stock (CMP)": f"{stock.split('.')[0]} ({cmp})",
        "10-day Low": low_10,
        "High Volume Zone": f"{high_vol_price} ({cmp})",
        "Today's Low": todays_low,
        "Yesterday's Low": yesterdays_low,
        "Status": status,
        "Perfect Confluence": perfect_confluence
    })

df = pd.DataFrame(table_data)

# --- Filter only Perfect Confluence = Yes ---
df_filtered = df[df["Perfect Confluence"] == "Yes"]

if df_filtered.empty:
    print("No stocks matching Perfect Confluence today.")
else:
    # --- Telegram credentials from GitHub Secrets ---
    BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
    CHAT_ID = os.environ.get("CHAT_ID")

    # --- Build stacked Telegram message ---
    message = ""
    for _, row in df_filtered.iterrows():
        todays_low_val = row["Today's Low"]
        yesterdays_low_val = row["Yesterday's Low"]

        message += f"<b>{row['Stock (CMP)']}</b>\n"
        message += f"10-day Low: {row['10-day Low']}\n"
        message += f"High Volume Zone: {row['High Volume Zone']}\n"
        message += f"Today's Low: {todays_low_val}\n"
        message += f"Yesterday's Low: {yesterdays_low_val}\n"
        message += f"Status: {row['Status']}\n"
        message += f"Perfect Confluence: {row['Perfect Confluence']}\n\n"

    # --- Send message to Telegram ---
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
        print("Telegram response:", response.json())
    except Exception as e:
        print("Telegram error:", repr(e))
