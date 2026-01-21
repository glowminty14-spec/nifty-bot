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
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
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
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # Weekend Check
    if now.weekday() >= 5:
        print("Today is Weekend. Market Closed.")
        return False

    # Market Hours Check (9:15 AM - 3:30 PM IST)
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
        # 1. Fetch Data
        df = yf.download(SYMBOL, period="5d", interval=INTERVAL, progress=False)

        # 2. DEBUG: Print columns to see what we got
        print(f"Raw Columns: {df.columns}")

        if df.empty:
            print("Data is empty. Yahoo might be blocking or no data available.")
            return

        # 3. SMART CLEANER (The Fix)
        # If columns are complex (MultiIndex), flatten them
        if isinstance(df.columns, pd.MultiIndex):
            # values(-1) gets the last level ('Close', 'Open') regardless of where Ticker is
            df.columns = df.columns.get_level_values(-1)
        
        # Double check if 'Close' exists now
        if "Close" not in df.columns:
            print(f"CRITICAL: 'Close' column missing. Available: {df.columns}")
            return

        if len(df) < 50:
            print("Not enough data points.")
            return

        # 4. Indicators
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        
        c = df.iloc[-1] 
        close = float(c["Close"])
        ema20 = c["EMA20"]
        ema50 = c["EMA50"]
        htf_bias = "BEARISH" if ema20 < ema50 else "BULLISH"
        
        print(f"Price: {close} | EMA20: {ema20:.2f} | Trend: {htf_bias}")

        # 5. Signal Logic
        msg = ""
        
        # CALL LOGIC
        if htf_bias == "BULLISH" and close > ema20:
            if c["Low"] <= ema20 and close > ema20:
                msg = f"🚀 <b>NIFTY CALL ALERT</b>\n\nPrice: {int(close)}\nTrigger: EMA20 Support\nTrend: BULLISH 🟢"

        # PUT LOGIC
        elif htf_bias == "BEARISH" and close < ema20:
            if c["High"] >= ema20 and close < ema20:
                msg = f"wv <b>NIFTY PUT ALERT</b>\n\nPrice: {int(close)}\nTrigger: EMA20 Rejection\nTrend: BEARISH 🔴"

        if msg:
            print("Signal Found! Sending Telegram...")
            send_telegram(msg)
        else:
            print("No signal right now.")

    except Exception as e:
        print(f"Error Details: {e}")

if __name__ == "__main__":
    # We allow it to run even if market is closed just to test the connection once
    run_strategy()
