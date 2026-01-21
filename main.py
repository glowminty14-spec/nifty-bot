import yfinance as yf
import pandas as pd
import requests
import os
import json
import subprocess
from datetime import datetime
import pytz

# ================= CONFIG =================
SYMBOL = "^NSEI"
INTERVAL = "15m"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
STATE_FILE = "trade_state.json"
# ==========================================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Telegram Fail: {e}")

# --- MEMORY FUNCTIONS ---
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return None

def save_state(data):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f)
    
    # Git Magic to save the file back to GitHub
    try:
        subprocess.run(["git", "config", "--global", "user.email", "bot@nifty.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "NiftyBot"], check=True)
        subprocess.run(["git", "add", STATE_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Update Trade State"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Trade State Saved to GitHub.")
    except Exception as e:
        print(f"⚠️ Could not save state to GitHub (Local test?): {e}")

def run_bot():
    print(f"Checking {SYMBOL}...")
    
    # 1. Fetch Data
    df = yf.download(SYMBOL, period="5d", interval=INTERVAL, progress=False)
    
    # Cleaner Logic
    if isinstance(df.columns, pd.MultiIndex):
        level_0 = df.columns.get_level_values(0)
        level_1 = df.columns.get_level_values(1) if df.columns.nlevels > 1 else []
        if "Close" in level_0: df.columns = level_0
        elif "Close" in level_1: df.columns = level_1

    if "Close" not in df.columns or len(df) < 50:
        print("Data Error.")
        return

    # Indicators
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()

    # Current Live Price
    current_price = float(df["Close"].iloc[-1])
    
    # Load Memory
    active_trade = load_state()

    # =========================================
    # PHASE 1: MANAGE ACTIVE TRADE (If exists)
    # =========================================
    if active_trade and active_trade["status"] == "OPEN":
        print(f"👀 Monitoring Active Trade: {active_trade['type']}")
        
        entry = active_trade["entry"]
        target = active_trade["target"]
        sl = active_trade["sl"]
        trade_type = active_trade["type"]
        
        result_msg = ""
        
        # Check CALL Exit
        if trade_type == "CALL":
            if current_price >= target:
                result_msg = f"🏆 <b>TARGET HIT!</b>\n\nType: CALL\nEntry: {entry}\nExit: {int(current_price)}\nResult: ✅ PROFIT"
            elif current_price <= sl:
                result_msg = f"❌ <b>STOP LOSS HIT</b>\n\nType: CALL\nEntry: {entry}\nExit: {int(current_price)}\nResult: 🔻 LOSS"
        
        # Check PUT Exit
        elif trade_type == "PUT":
            if current_price <= target:
                result_msg = f"🏆 <b>TARGET HIT!</b>\n\nType: PUT\nEntry: {entry}\nExit: {int(current_price)}\nResult: ✅ PROFIT"
            elif current_price >= sl:
                result_msg = f"❌ <b>STOP LOSS HIT</b>\n\nType: PUT\nEntry: {entry}\nExit: {int(current_price)}\nResult: 🔻 LOSS"

        if result_msg:
            send_telegram(result_msg)
            # Clear memory (Trade Closed)
            save_state({"status": "CLOSED"})
        else:
            print("Trade still running...")
        
        return  # Stop here. Don't look for new trades if one is open.

    # =========================================
    # PHASE 2: HUNT FOR NEW TRADES
    # =========================================
    c = df.iloc[-2] # Closed Candle
    close = float(c["Close"])
    open_ = float(c["Open"])
    ema20 = c["EMA20"]
    ema50 = c["EMA50"]
    
    htf_bias = "BEARISH" if ema20 < ema50 else "BULLISH"
    new_trade = None

    if htf_bias == "BULLISH":
        if c["Low"] <= ema20 and close > ema20 and close > open_:
            sl = int(c["Low"] - 5)
            target = int(close + (close - sl) * 2)
            new_trade = {"type": "CALL", "entry": int(close), "sl": sl, "target": target}

    elif htf_bias == "BEARISH":
        if c["High"] >= ema20 and close < ema20 and close < open_:
            sl = int(c["High"] + 5)
            target = int(close - (sl - close) * 2)
            new_trade = {"type": "PUT", "entry": int(close), "sl": sl, "target": target}

    if new_trade:
        msg = (
            f"🚀 <b>NEW {new_trade['type']} ENTRY</b>\n\n"
            f"💰 Price: {new_trade['entry']}\n"
            f"🛑 SL: {new_trade['sl']}\n"
            f"🎯 Target: {new_trade['target']}"
        )
        send_telegram(msg)
        
        # Save Trade to Memory
        new_trade["status"] = "OPEN"
        save_state(new_trade)
    else:
        print("No new setup.")

if __name__ == "__main__":
    run_bot()
