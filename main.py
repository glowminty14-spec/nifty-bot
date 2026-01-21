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

        # 2. DEBUG: Print raw structure (Helps us see if Yahoo changes things)
        print(f"Raw Columns: {df.columns}")

        if df.empty:
            print("Data is empty.")
            return

        # ==================================================
        # 3. THE CRITICAL FIX (The Cleaner)
        # ==================================================
        # This block looks for "Close" in all levels of the column headers
        if isinstance(df.columns, pd.MultiIndex):
            level_0 = df.columns.get_level_values(0)
            level_1 = df.columns.get_level_values(1) if df.columns.nlevels > 1 else []
            
            # Check which level has the price data and use that one
            if "Close" in level_0:
                df.columns = level_0
            elif "Close" in level_1:
                df.columns = level_1
        
        # Final Check: If we still don't have "Close", stop here.
        if "Close" not in df.columns:
            print(f"CRITICAL: Still couldn't find 'Close'. Columns are: {df.columns}")
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
        
        print(f"SUCCESS: Price: {int(close)} | EMA20: {int(ema20)} | Trend: {htf_bias}")

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
    run_strategy()
