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
    if status == "Near HVZ" and todays_low <= high_vol_price and todays_low >= yesterdays_low:
        perfect_confluence = "Yes"
    else:
        perfect_confluence = "No"

    table_data.append({
        "Stock_CMP": f"{stock.split('.')[0]} ({cmp})",
        "Low_10d": low_10,
        "High_Volume_Zone": f"{high_vol_price} ({cmp})",
        "Todays_Low": todays_low,
        "Yesterdays_Low": yesterdays_low,
        "Status": status,
        "Perfect_Confluence": perfect_confluence
    })

df = pd.DataFrame(table_data)

# --- Filter only Perfect Confluence = Yes ---
df_filtered = df[df["Perfect_Confluence"] == "Yes"]

if df_filtered.empty:
    message = "No stocks meeting Perfect Confluence at this time."
else:
    # --- Build stacked Telegram message ---
    message = ""
    for _, row in df_filtered.iterrows():
        message += f"<b>{row['Stock_CMP']}</b>\n"
        message += f"10-day Low: {row['Low_10d']}\n"
        message += f"High Volume Zone: {row['High_Volume_Zone']}\n"
        message += f"Today's Low: {row['Todays_Low']}\n"
        message += f"Yesterday's Low: {row['Yesterdays_Low']}\n"
        message += f"Status: {row['Status']}\n"
        message += f"Perfect Confluence: {row['Perfect_Confluence']}\n\n"

# --- Send message to Telegram ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
payload = {
    "chat_id": CHAT_ID,
    "text": message,
    "parse_mode": "HTML"
}

response = requests.post(url, data=payload)
print(response.json())  # confirms if message sent successfully
