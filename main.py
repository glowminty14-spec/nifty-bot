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

# --- NEW SETTINGS FOR INTRADAY ---
NO_NEW_TRADES_AFTER = "14:30"  # 2:30 PM IST (Don't enter late)
AUTO_SQUARE_OFF_TIME = "15:15" # 3:15 PM IST (Force close everything)
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
    
    # Save to GitHub
    try:
        subprocess.run(["git", "config", "--global", "user.email", "bot@nifty.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "NiftyBot"], check=True)
        subprocess.run(["git", "add", STATE_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Update Trade State"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Trade State Saved.")
    except Exception as e:
        print(f"⚠️ Save Error: {e}")

def run_bot():
    print(f"Checking {SYMBOL}...")
    
    # --- 1. GET TIME (IST) ---
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    current_time_str = now.strftime("%H:%M")
    print(f"Current Time (IST): {current_time_str}")

    # --- 2. FETCH DATA ---
    df = yf.download(SYMBOL, period="5d", interval=INTERVAL, progress=False)
    
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
    current_price = float(df["Close"].iloc[-1])
    
    active_trade = load_state()

    # =========================================
    # PHASE 1: MANAGE OPEN TRADES (Logic Updated)
    # =========================================
    if active_trade and active_trade["status"] == "OPEN":
        entry = active_trade["entry"]
        target = active_trade["target"]
        sl = active_trade["sl"]
        trade_type = active_trade["type"]
        
        result_msg = ""
        
        # --- RULE 1: CHECK AUTO SQUARE OFF TIME ---
        if current_time_str >= AUTO_SQUARE_OFF_TIME:
            result_msg = (
                f"⚠️ <b>INTRADAY AUTO-SQUARE OFF</b>\n\n"
                f"🕒 Time: {current_time_str}\n"
                f"Type: {trade_type}\n"
                f"Entry: {entry}\n"
                f"Exit: {int(current_price)}\n"
                f"Reason: Market Closing Soon"
            )
        
        # --- RULE 2: CHECK TARGET / SL ---
        elif trade_type == "CALL":
            if current_price >= target:
                result_msg = f"🏆 <b>TARGET HIT</b>\n\nType: CALL\nEntry: {entry}\nExit: {int(current_price)}\nResult: ✅ PROFIT"
            elif current_price <= sl:
                result_msg = f"❌ <b>STOP LOSS HIT</b>\n\nType: CALL\nEntry: {entry}\nExit: {int(current_price)}\nResult: 🔻 LOSS"
        
        elif trade_type == "PUT":
            if current_price <= target:
                result_msg = f"🏆 <b>TARGET HIT</b>\n\nType: PUT\nEntry: {entry}\nExit: {int(current_price)}\nResult: ✅ PROFIT"
            elif current_price >= sl:
                result_msg = f"❌ <b>STOP LOSS HIT</b>\n\nType: PUT\nEntry: {entry}\nExit: {int(current_price)}\nResult: 🔻 LOSS"

        # CLOSE TRADE IF ANY CONDITION MET
        if result_msg:
            send_telegram(result_msg)
            save_state({"status": "CLOSED"})
        else:
            print(f"Trade Open. Time is {current_time_str}, waiting for exit or 15:15.")
        
        return  # Stop here if we have an open trade

    # =========================================
    # PHASE 2: NEW TRADE HUNT (Logic Updated)
    # =========================================
    
    # --- RULE 3: CHECK ENTRY CUTOFF TIME ---
    if current_time_str >= NO_NEW_TRADES_AFTER:
        print(f"Time is {current_time_str}. Too late for new trades. (Cutoff: {NO_NEW_TRADES_AFTER})")
        return

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
            f"🕒 Time: {current_time_str}\n"
            f"💰 Price: {new_trade['entry']}\n"
            f"🛑 SL: {new_trade['sl']}\n"
            f"🎯 Target: {new_trade['target']}"
        )
        send_telegram(msg)
        new_trade["status"] = "OPEN"
        save_state(new_trade)
    else:
        print("No new setup.")

if __name__ == "__main__":
    run_bot()
