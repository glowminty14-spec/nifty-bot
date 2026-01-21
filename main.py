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
    data = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": message,
        "parse_mode": "HTML" # Added HTML support for bold text
    }
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Telegram Fail: {e}")

def run_strategy():
    print(f"Checking {SYMBOL}...")
    try:
        # 1. Fetch Data
        df = yf.download(SYMBOL, period="5d", interval=INTERVAL, progress=False)

        if df.empty:
            print("Data is empty.")
            return

        # 2. THE BULLETPROOF CLEANER (Keep this!)
        if isinstance(df.columns, pd.MultiIndex):
            level_0 = df.columns.get_level_values(0)
            level_1 = df.columns.get_level_values(1) if df.columns.nlevels > 1 else []
            
            if "Close" in level_0:
                df.columns = level_0
            elif "Close" in level_1:
                df.columns = level_1
        
        if "Close" not in df.columns:
            print("CRITICAL: Column fix failed.")
            return

        if len(df) < 50:
            print("Not enough data.")
            return

        # 3. Indicators
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()

        # 4. STRATEGY (Using Closed Candle for Safety)
        # We look at the candle that JUST finished (iloc[-2])
        c = df.iloc[-2]
        
        # Formatting Time for the alert
        candle_time = c.name.strftime("%H:%M") 

        close = float(c["Close"])
        open_ = float(c["Open"])
        high = float(c["High"])
        low = float(c["Low"])
        ema20 = c["EMA20"]
        ema50 = c["EMA50"]
        
        htf_bias = "BEARISH" if ema20 < ema50 else "BULLISH"
        msg = ""

        # CALL LOGIC (Bullish)
        if htf_bias == "BULLISH":
            # Rule: Price dipped to EMA20 and rejected (wick)
            pullback = low <= ema20
            rejection = close > ema20 and close > open_ # Green Candle
            
            if pullback and rejection:
                sl = int(low - 5)
                target = int(close + (close - sl) * 2)
                
                msg = (
                    f"🚀 <b>NIFTY CALL ALERT</b>\n\n"
                    f"🕒 Time: {candle_time}\n"
                    f"💰 Price: {int(close)}\n"
                    f"🛑 SL: {sl}\n"
                    f"🎯 Target: {target}\n"
                    f"⚡ Trigger: EMA20 Support"
                )

        # PUT LOGIC (Bearish)
        elif htf_bias == "BEARISH":
            # Rule: Price rallied to EMA20 and rejected (wick)
            pullback = high >= ema20
            rejection = close < ema20 and close < open_ # Red Candle
            
            if pullback and rejection:
                sl = int(high + 5)
                target = int(close - (sl - close) * 2)
                
                msg = (
                    f"🔻 <b>NIFTY PUT ALERT</b>\n\n"
                    f"🕒 Time: {candle_time}\n"
                    f"💰 Price: {int(close)}\n"
                    f"🛑 SL: {sl}\n"
                    f"🎯 Target: {target}\n"
                    f"⚡ Trigger: EMA20 Rejection"
                )

        if msg:
            print(f"Signal Found: {htf_bias}")
            send_telegram(msg)
        else:
            print(f"Analyzed candle {candle_time}: No Trade.")

    except Exception as e:
        print(f"Error Details: {e}")

if __name__ == "__main__":
    run_strategy()
