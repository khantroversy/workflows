#-----------------------------
# Step 0: Install required packages
# pip install websocket-client pandas streamlit yfinance tabulate --quiet
# -----------------------------

import websocket, json, threading, time, os
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
from queue import Queue, Empty
import yfinance as yf
import atexit

# -----------------------------
# Step 1: Configuration
# -----------------------------
SYMBOLS = ["BTCUSDT", "ETHUSDT"]  # tracked coins
# Track last write time per symbol for burst CSV
last_burst_write = {sym: {'buy': None, 'sell': None} for sym in SYMBOLS}
WINDOW_MINUTES = 5
rolling_window = {sym: [] for sym in SYMBOLS}  # rolling ticks
burst_state = {sym: {'buy': {}, 'sell': {}} for sym in SYMBOLS}
history_snapshots = []

message_queue = Queue()
status_queue = Queue()
error_queue = Queue()
notification_queue = Queue()
# Thresholds (example, adjust as per internet references / volatility)
STATIC_THRESHOLD = {
    "BTCUSDT": 5.0,  # approximate threshold for large trades
    "ETHUSDT": 20
}

CSV_FILE = "live_market_data.csv"
BURST_CSV_FILE = "burst_ticks.csv"


def notify_browser(title, message):
    st.experimental_get_query_params()  # ensure Streamlit session context
    st.toast(f"{title}: {message}")  # simpler way; or use st_javascript if you want JS notifications


# -----------------------------
# Step 2: Streamlit UI placeholders
# -----------------------------
st.markdown("<h3 style='margin-top:5px; padding-top:0;'>Live Crypto Data</h3>", unsafe_allow_html=True)
table_placeholder = st.empty()
status_placeholder = st.empty()
error_placeholder = st.empty()
history_placeholder = st.empty()
st.markdown("""
<style>
.st-emotion-cache-1w723zb {
    max-width: 1024px;
    padding:50px 0 0 0;
}
</style>
""", unsafe_allow_html=True)
# -----------------------------
# Step 3: Fetch Yahoo Finance lows (fixed)
# -----------------------------
def fetch_yahoo_lows(symbols_list):
    yahoo_map = {}
    symbol_yf_map = {
        "BTCUSDT": "BTC-USD",
        "ETHUSDT": "ETH-USD"
    }
    for sym in symbols_list:
        ticker = symbol_yf_map.get(sym, sym + "-USD")
        try:
            data = yf.Ticker(ticker).history(period="10d")
            if data.empty:
                raise ValueError("No data found")
            today_low = round(data['Low'].iloc[-1], 2)
            ten_day_low = round(data['Low'].iloc[-10:].min(), 2)
            yahoo_map[sym] = {"Today Low": today_low, "10D Low": ten_day_low}
        except Exception as e:
            print(f"Yahoo fetch error for {sym}: {e}")
            yahoo_map[sym] = {"Today Low": None, "10D Low": None}
    return yahoo_map

yahoo_lows = fetch_yahoo_lows(SYMBOLS)


# -----------------------------
# Step 4: CSV utilities
# -----------------------------
CSV_COLUMNS = ["Timestamp", "Symbol", "LTP", "Buy LTQ", "Sell LTQ", "Net Flow",
               "Buy Burst", "Sell Burst", "Divergence", "Manipulation @LTP",
               "Today Low", "10D Low"]

def append_snapshot_to_csv(snapshot_df):
    snapshot_df = snapshot_df[CSV_COLUMNS]
    write_header = not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0
    snapshot_df.to_csv(CSV_FILE, mode='a', index=False, header=write_header)

def append_burst_tick(symbol_name, ltp, buy_ltq, sell_ltq, timestamp):
    global last_burst_write

    write_row = False

    # Check buy burst
    last_buy_time = last_burst_write[symbol_name]['buy']
    current_milli = timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")
    last_buy_milli = last_buy_time.strftime("%Y-%m-%d %H:%M:%S.%f") if last_buy_time else None
    if buy_ltq >= 0 and current_milli != last_buy_milli:
        write_row = True
        last_burst_write[symbol_name]['buy'] = timestamp

    # Check sell burst
    last_sell_time = last_burst_write[symbol_name]['sell']
    last_sell_milli = last_sell_time.strftime("%Y-%m-%d %H:%M:%S.%f") if last_sell_time else None
    if sell_ltq >= 0 and current_milli != last_sell_milli:
        write_row = True
        last_burst_write[symbol_name]['sell'] = timestamp

    if write_row:
        record = {
            "Time": timestamp.strftime("%Y-%m-%d %H:%M:%S.%f"),
            "Symbol": symbol_name,
            "LTP": ltp,
            "Buy Burst": buy_ltq if buy_ltq >= 0 else "-",
            "Sell Burst": sell_ltq if sell_ltq >= 0 else "-"
        }
        df = pd.DataFrame([record])
        write_header = not os.path.exists(BURST_CSV_FILE) or os.path.getsize(BURST_CSV_FILE) == 0
        df.to_csv(BURST_CSV_FILE, mode='a', index=False, header=write_header)

# -----------------------------
# Step 4b: Browser Notification
# -----------------------------
def notify_browser(title, message):
    """
    Streamlit browser notification using JS
    """
    js = f"""
    <script>
    if (Notification.permission === 'granted') {{
        new Notification("{title}", {{ body: "{message}" }});
    }} else if (Notification.permission !== 'denied') {{
        Notification.requestPermission().then(function(permission) {{
            if (permission === 'granted') {{
                new Notification("{title}", {{ body: "{message}" }});
            }}
        }});
    }}
    </script>
    """
    st.components.v1.html(js, height=0)


# -----------------------------
# Step 5: Update table
# -----------------------------
def update_table(symbol):
    now = datetime.now()
    ticks = rolling_window.get(symbol, [])

    # ⛔ Don't filter ticks by time here, keep them all
    # rolling_window[symbol] = [t for t in ticks if now - t['timestamp'] <= timedelta(minutes=WINDOW_MINUTES)]
    # ticks = rolling_window[symbol]

    threshold = STATIC_THRESHOLD.get(symbol, 0)

    if not ticks:
        burst_state[symbol] = {'buy': {}, 'sell': {}}
        row = {
            "Symbol": symbol,
            "LTP": 0,
            "Buy LTQ": 0,
            "Sell LTQ": 0,
            "Net Flow": 0,
            "Buy Burst": "-",
            "Sell Burst": "-",
            "Divergence": "-",
            "Manipulation @LTP": "-",
            "Today Low": yahoo_lows.get(symbol, {}).get("Today Low"),
            "10D Low": yahoo_lows.get(symbol, {}).get("10D Low")
        }
        return row

    last_tick = ticks[-1]
    ltp = last_tick['ltp']
    buy_ltq = last_tick['buy_ltq']
    sell_ltq = last_tick['sell_ltq']

    # ✅ Accumulate all ticks (no cutoff)
    total_buy = sum(t['buy_ltq'] for t in ticks)
    total_sell = sum(t['sell_ltq'] for t in ticks)

    net_flow = total_buy - total_sell
    current_time = last_tick['timestamp']

    if symbol not in burst_state:
        burst_state[symbol] = {'buy': {}, 'sell': {}}

    # Buy burst logic
    buy_burst_str = "-"
    buy_state = burst_state[symbol]['buy']
    if buy_ltq >= threshold:
        if not buy_state.get('start_time'):
            buy_state['start_time'] = current_time
            # 🚨 Trigger notification only once per new burst
            if not buy_state.get('notified', False):
                notification_queue.put((f"{symbol} Buy Burst 🚀", f"Buy burst of {buy_ltq} LTQ started!"))
                buy_state['notified'] = True
        duration_sec = int((current_time - buy_state['start_time']).total_seconds())
        buy_burst_str = f"{buy_ltq} ({duration_sec} sec)"
        buy_state['ongoing'] = True
    else:
        buy_state['start_time'] = None
        buy_state['ongoing'] = False
        buy_state['notified'] = False  # reset for next burst

    # Sell burst logic
    sell_burst_str = "-"
    sell_state = burst_state[symbol]['sell']
    if sell_ltq >= threshold:
        if not sell_state.get('start_time'):
            sell_state['start_time'] = current_time
            if not sell_state.get('notified', False):
                notification_queue.put((f"{symbol} Sell Burst ⚡", f"Sell burst of {sell_ltq} LTQ started!"))
                sell_state['notified'] = True
        duration_sec = int((current_time - sell_state['start_time']).total_seconds())
        sell_burst_str = f"{sell_ltq} ({duration_sec} sec)"
        sell_state['ongoing'] = True
    else:
        sell_state['start_time'] = None
        sell_state['ongoing'] = False
        sell_state['notified'] = False

    # Divergence / Manipulation (still uses rolling last two ticks only)
    if len(ticks) >= 2:
        prev_price = ticks[-2]['ltp']
        price_change = ltp - prev_price
        if net_flow < 0 and price_change > 0:
            divergence = "Absorption / Hidden Buying"
        elif net_flow > 0 and price_change < 0:
            divergence = "Distribution / Hidden Selling"
        else:
            divergence = "-"
        manipulation_flag = "High" if divergence in ["Absorption / Hidden Buying", "Distribution / Hidden Selling"] else "-"
    else:
        divergence = "-"
        manipulation_flag = "-"

    # Append burst tick to CSV
    if buy_burst_str != "-" or sell_burst_str != "-":
        append_burst_tick(symbol, ltp,
                          buy_ltq if buy_burst_str != "-" else -1,
                          sell_ltq if sell_burst_str != "-" else -1,
                          current_time)

    row = {
        "Symbol": symbol,
        "LTP": ltp,
        "Buy LTQ": total_buy,   # ✅ full accumulation
        "Sell LTQ": total_sell, # ✅ full accumulation
        "Net Flow": net_flow,
        "Buy Burst": buy_burst_str,
        "Sell Burst": sell_burst_str,
        "Divergence": divergence,
        "Manipulation @LTP": manipulation_flag,
        "Today Low": yahoo_lows.get(symbol, {}).get("Today Low"),
        "10D Low": yahoo_lows.get(symbol, {}).get("10D Low")
    }
    return row

# -----------------------------
# Step 6: WebSocket callbacks
# -----------------------------
window_start_time = datetime.now()

def on_message(ws, message):
    global window_start_time
    data = json.loads(message)
    if 'data' in data and 's' in data['data']:
        sym = data['data']['s'].upper()
        if sym not in SYMBOLS:
            return
        ltp = float(data['data']['p'])
        qty = float(data['data']['q'])

        # Buy or sell assignment based on maker flag
        if data['data']['m']:  # sell
            sell_ltq = qty
            buy_ltq = 0
        else:
            buy_ltq = qty
            sell_ltq = 0

        tick_entry = {
            "timestamp": datetime.now(),
            "ltp": ltp,
            "buy_ltq": buy_ltq,
            "sell_ltq": sell_ltq,
            "divergence": None
        }
        rolling_window[sym].append(tick_entry)

    

    # 15-min snapshot logic
    now = datetime.now()
    if (now - window_start_time).total_seconds() >= WINDOW_MINUTES*60:
        rows = [update_table(sym) for sym in SYMBOLS]
        snapshot_df = pd.DataFrame(rows)
        snapshot_df.insert(0, "Timestamp", now.strftime("%Y-%m-%d %H:%M"))
        append_snapshot_to_csv(snapshot_df)
        history_snapshots.append(snapshot_df)
        # Clear ticks
        for sym in SYMBOLS:
            rolling_window[sym] = []
        window_start_time = now

    # Push latest rolling snapshot to Streamlit
    rows = [update_table(sym) for sym in SYMBOLS]    
    
    
    message_queue.put(pd.DataFrame(rows))

def on_error(ws, error):
    error_queue.put(f"❌ WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    status_queue.put(("warning", f"🔴 WebSocket closed: {close_status_code}"))

def on_open(ws):
    status_queue.put(("info", "🟢 WebSocket connected"))

# -----------------------------
# Step 7: Streamlit display loop
# -----------------------------
def streamlit_loop():
    while True:
        # -------------------- Notifications --------------------
        try:
            while True:  # keep fetching until queue is empty
                title, msg = notification_queue.get_nowait()
                notify_browser(title, msg)
        except Empty:
            pass

        # -------------------- Table updates --------------------
        try:
            df = message_queue.get_nowait()
            table_placeholder.dataframe(df)
        except Empty:
            pass

        # -------------------- Errors --------------------
        try:
            err = error_queue.get_nowait()
            error_placeholder.error(err)
        except Empty:
            pass

        # -------------------- Status --------------------
        try:
            stat = status_queue.get_nowait()
            type_, msg = stat
            if type_ == "info":
                status_placeholder.info(msg)
            elif type_ == "warning":
                status_placeholder.warning(msg)
        except Empty:
            pass

        # -------------------- History UI --------------------
        if history_snapshots:
            cumulative_ui = {}
            for snapshot in history_snapshots:
                for _, row in snapshot.iterrows():
                    sym = row["Symbol"]
                    if sym not in cumulative_ui:
                        cumulative_ui[sym] = row.to_dict()
                    else:
                        cumulative_ui[sym]["Buy LTQ"] += row["Buy LTQ"]
                        cumulative_ui[sym]["Sell LTQ"] += row["Sell LTQ"]
                        cumulative_ui[sym]["Net Flow"] += row["Net Flow"]
                        cumulative_ui[sym]["LTP"] = row["LTP"]
                        cumulative_ui[sym]["Buy Burst"] = row["Buy Burst"]
                        cumulative_ui[sym]["Sell Burst"] = row["Sell Burst"]
                        cumulative_ui[sym]["Divergence"] = row["Divergence"]
                        cumulative_ui[sym]["Manipulation @LTP"] = row["Manipulation @LTP"]
                        cumulative_ui[sym]["Today Low"] = row["Today Low"]
                        cumulative_ui[sym]["10D Low"] = row["10D Low"]
            ui_history_df = pd.DataFrame(cumulative_ui.values())
            history_placeholder.dataframe(ui_history_df)

        time.sleep(0.2)

# -----------------------------
# Step 8: Exit handler
# -----------------------------
def exit_handler():
    try:
        if rolling_window:
            rows = [update_table(sym) for sym in SYMBOLS]
            snapshot_df = pd.DataFrame(rows)
            snapshot_df.insert(0, "Timestamp", datetime.now().strftime("%Y-%m-%d %H:%M"))
            append_snapshot_to_csv(snapshot_df)
            print("✅ Live table appended to CSV on exit.")
    except Exception as e:
        print(f"❌ Error on exit snapshot: {e}")

atexit.register(exit_handler)

# -----------------------------
# Step 9: Start WebSocket
# -----------------------------
streams = "/".join([f"{s.lower()}@trade" for s in SYMBOLS])
ws_url = f"wss://stream.binance.com:9443/stream?streams={streams}"
ws = websocket.WebSocketApp(ws_url,
                            on_open=on_open,
                            on_message=on_message,
                            on_error=on_error,
                            on_close=on_close)
threading.Thread(target=ws.run_forever, daemon=True).start()

# -----------------------------
# Step 10: Streamlit heartbeat thread
# -----------------------------
def heartbeat():
    while True:
        status_queue.put(("info", f"💓 Heartbeat: {time.strftime('%H:%M:%S')}"))
        time.sleep(5)

threading.Thread(target=heartbeat, daemon=True).start()

# -----------------------------
# Step 11: Run Streamlit loop
# -----------------------------
try:
    streamlit_loop()
except KeyboardInterrupt:
    exit_handler()
    print("✅ Exiting via Ctrl+C")
