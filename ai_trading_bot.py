import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Portni zudlik bilan ochish uchun server
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# Dastur ishga tushishi bilan birinchi bo'lib portni ochamiz
threading.Thread(target=run_server, daemon=True).start()

import json
import os
import time
import urllib.parse
import urllib.request
import joblib
import pandas as pd
import warnings
warnings.filterwarnings('ignore') # Ortiqcha UserWarning'larni berkitish

# ==========================================
# SOZLAMALAR
# ==========================================
TELEGRAM_BOT_TOKEN = "8995984666:AAGxyfEtjB3JLKlN3NToL6exQOgrFCSoMo0"  # BotFather Token
TELEGRAM_CHAT_ID = "1273647109"              # Chat ID

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "NEARUSDT", "AVAXUSDT"]
BALANCE_USDT = 50.0
BUY_PERCENTAGE = 0.20
PROFIT_TARGET = 0.01  # 1% foyda
COOLDOWN_SECONDS = 180

active_orders = []
last_buy_times = {symbol: 0 for symbol in SYMBOLS}

# AI Modelni yuklash
print("AI Model yuklanmoqda...")
model = joblib.load("crypto_ai_model.pkl")

def send_telegram(message):
    """Telegram'ga xabar yuborish va xatolikni batafsil ko'rsatish"""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        return

    token = str(TELEGRAM_BOT_TOKEN).strip()
    chat_id = str(TELEGRAM_CHAT_ID).strip()
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    try:
        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req) as response:
            pass
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"\n⚠️ Telegram Xatosi ({e.code}): {error_body}\n")
    except Exception as e:
        print(f"Telegram ulanishda xatolik: {e}")
def get_klines_and_features(symbol):
    """Binance'dan oxirgi shamlarni olib AI uchun feature tayyorlash"""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=50"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            df = pd.DataFrame(data, columns=[
                'time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'qav', 'num_trades', 'tbb', 'tbq', 'ignore'
            ])
            df['close'] = df['close'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['volume'] = df['volume'].astype(float)

            df['return'] = df['close'].pct_change()
            df['sma_10'] = df['close'].rolling(10).mean()
            df['sma_30'] = df['close'].rolling(30).mean()

            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))

            features_list = ['return', 'sma_10', 'sma_30', 'rsi', 'volume']
            latest = df[features_list].iloc[[-1]] # Ustun nomlari bilan DataFrame ko'rinishida olish
            
            return df['close'].iloc[-1], latest
    except Exception:
        return None, None

def run_ai_bot():
    global BALANCE_USDT

    start_msg = f"🤖 AI Trading Bot ishga tushdi!\nBoshlang'ich Balans: ${BALANCE_USDT}"
    print(start_msg)
    send_telegram(start_msg)

    while True:
        for symbol in SYMBOLS:
            price, features_df = get_klines_and_features(symbol)

            if price and features_df is not None:
                # Model orqali ehtimollikni hisoblash
                prob = model.predict_proba(features_df)[0][1]
                current_time = time.time()

                print(f"[SCANNER] {symbol}: ${price:.2f} | AI O'sish Ehtimoli: {prob*100:.1f}%")

                # BUY SIGNAL: Model ehtimoli 65% dan yuqori bo'lsa
                if prob >= 0.65 and BALANCE_USDT >= 5.0 and (current_time - last_buy_times[symbol]) > COOLDOWN_SECONDS:
                    trade_amount = BALANCE_USDT * BUY_PERCENTAGE
                    amount_bought = trade_amount / price
                    BALANCE_USDT -= trade_amount
                    target_price = price * (1 + PROFIT_TARGET)

                    active_orders.append({
                        "symbol": symbol,
                        "buy_price": price,
                        "target_price": target_price,
                        "amount": amount_bought
                    })

                    last_buy_times[symbol] = current_time
                    buy_msg = (
                        f"🟢 AI XARID QILDI!\n"
                        f"Juftlik: {symbol}\n"
                        f"Narx: ${price:.2f}\n"
                        f"Ehtimollik: {prob*100:.1f}%\n"
                        f"Maqsad: ${target_price:.2f}"
                    )
                    print(f"\n{buy_msg}\n")
                    send_telegram(buy_msg)

                # SELL CHECK
                for order in active_orders[:]:
                    if order["symbol"] == symbol and price >= order["target_price"]:
                        usdt_gained = order["amount"] * price
                        BALANCE_USDT += usdt_gained
                        profit = usdt_gained - (order["amount"] * order["buy_price"])

                        sell_msg = (
                            f"🔴 FOYDA FIKSATSIYA QILINDI!\n"
                            f"Juftlik: {symbol}\n"
                            f"Sotuv narxi: ${price:.2f}\n"
                            f"Foyda: +${profit:.3f}\n"
                            f"Joriy Balans: ${BALANCE_USDT:.2f}"
                        )
                        print(f"\n{sell_msg}\n")
                        send_telegram(sell_msg)
                        active_orders.remove(order)

            time.sleep(2)

if __name__ == "__main__":
    run_ai_bot()
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Render talab qiladigan portni ochish uchun veb-server
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Crypto Bot is alive and running!")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# Veb-serverni alohida oqimda (thread) ishga tushiramiz
threading.Thread(target=run_server, daemon=True).start()

import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# 1. Render talab qiladigan portni zudlik bilan ochuvchi veb-server
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Crypto Bot is alive and running!")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# 2. Asosiy savdo botini va Telegram polling'ni ishga tushiruvchi funksiya
def start_trading_bot():
    # Bu yerda sizning eski botingiz kodlari / infinity_polling() turishi kerak
    print("Trading bot started...")
    # Masalan: bot.infinity_polling()

if __name__ == "__main__":
    # Veb-serverni fon oqimida (thread) ishga tushiramiz (Render portni darhol ko'rishi uchun)
    threading.Thread(target=run_server, daemon=True).start()
    
    # Asosiy jarayonda esa savdo botini yurgizamiz
    start_trading_bot()

if __name__ == "__main__":
    print("Telegram bot ishga tushdi va xabarlarni kutmoqda...")
    bot.infinity_polling()
