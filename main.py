import yfinance as yf
import pandas as pd
import requests
import os
import sys
from datetime import datetime
import pytz

# ================= CONFIG =================
SYMBOL = "^NSEI"
INTERVAL = "15m"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") # We will set these in GitHub later
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
# ==========================================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram Fail: {e}")

def check_market_open():
    # Define IST Timezone
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # 1. Check Weekend (Saturday=5, Sunday=6)
    if now.weekday() >= 5:
        print("Today is Weekend. Market Closed.")
        return False

    # 2. Check Market Hours (09:15 to 15:30)
    current_time = now.time()
    start_time = datetime.strptime("09:15", "%H:%M").time()
    end_time = datetime.strptime("15:30", "%H:%M").time()

    if not (start_time <= current_time <= end_time):
        print(f"Market Closed. Current time: {current_time}")
        return False
        
    return True

def run_strategy():
    print(f"Checking {SYMBOL}...")
    try:
        # Fetch Data (Use curl_cffi method if needed, but standard usually works on GitHub servers)
        df = yf.download(SYMBOL, period="5d", interval=INTERVAL, progress=False)
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(1)

        if df.empty or len(df) < 50:
            print("Not enough data.")
            return

        # Indicators
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        
        c = df.iloc[-1] # Current Candle
        p = df.iloc[-2] # Previous Candle (Closed)
        
        close = float(c["Close"])
        ema20 = c["EMA20"]
        ema50 = c["EMA50"]
        htf_bias = "BEARISH" if ema20 < ema50 else "BULLISH"
        
        # LOGIC: We check the *Just Closed* candle (p) or *Current Live* (c)
        # For alerts, it's safer to check if the LIVE price is crossing
        
        msg = ""
        
        # CALL LOGIC
        if htf_bias == "BULLISH" and close > ema20:
            # Price dipped near EMA20 and is now bouncing up
            if c["Low"] <= ema20 and close > ema20:
                msg = f"🚀 <b>NIFTY CALL ALERT</b>\n\nPrice: {int(close)}\nTrigger: EMA20 Support\nTrend: BULLISH 🟢"

        # PUT LOGIC
        elif htf_bias == "BEARISH" and close < ema20:
            # Price rallied to EMA20 and is rejecting down
            if c["High"] >= ema20 and close < ema20:
                msg = f"wv <b>NIFTY PUT ALERT</b>\n\nPrice: {int(close)}\nTrigger: EMA20 Rejection\nTrend: BEARISH 🔴"

        if msg:
            print("Signal Found! Sending Telegram...")
            send_telegram(msg)
        else:
            print("No signal right now.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if check_market_open():
        run_strategy()
