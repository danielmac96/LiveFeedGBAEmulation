import asyncio
import json
import websockets
import time
import random
import socket

# --- Datafeed ---
GBA_HOST = "127.0.0.1"
GBA_PORT = 8888
# Map your full names to the specific characters your Lua script expects
BTN_MAP = {
    "A": "A", "B": "B", "START": "S", "SELECT": "s",
    "RIGHT": ">", "LEFT": "<", "UP": "^", "DOWN": "v",
    "L": "L", "R": "R"
}

# Shared Queues
trade_queue = asyncio.Queue()
button_queue = asyncio.Queue()


async def get_coinbase_feed(symbol="BTC-USD"):
    """Fetch live trades from Coinbase WebSocket."""
    url = "wss://ws-feed.exchange.coinbase.com"
    async with websockets.connect(url) as ws:
        subscribe = {
            "type": "subscribe",
            "product_ids": [symbol],
            "channels": ["ticker"]
        }
        await ws.send(json.dumps(subscribe))
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            if data.get("type") == "ticker":
                await trade_queue.put(data)


async def gba_logic_mapper():
    """Analyze trade batches, log the 'Why', and queue randomized buttons."""
    batch = []
    last_batch_time = time.time()

    while True:
        try:
            data = await asyncio.wait_for(trade_queue.get(), timeout=0.1)
            batch.append({
                "price": float(data["price"]),
                "size": float(data.get("last_size", 0)),
                "side": data.get("side")
            })
        except (asyncio.TimeoutError, TimeoutError):
            pass
        except Exception as e:
            print(f"Data Collection Error: {e}")

        # Evaluation Window
        if time.time() - last_batch_time >= 2.0:
            if len(batch) > 0:
                try:
                    # --- Metrics ---
                    start_p, end_p = batch[0]["price"], batch[-1]["price"]
                    delta = ((end_p - start_p) / start_p) * 100
                    prices = [d["price"] for d in batch]
                    volatility = max(prices) - min(prices)
                    buys = len([d for d in batch if d["side"] == "buy"])
                    sells = len(batch) - buys
                    max_trade = max(d["size"] for d in batch)
                    trade_count = len(batch)

                    # We use a simple list of button names now
                    actions = []

                    # --- Logic Engine ---
                    if buys > sells:    actions.append("RIGHT")
                    if sells > buys:   actions.append("LEFT")
                    if delta > 0:       actions.append("A")
                    if delta <= 0:      actions.append("B")
                    if trade_count > 5:
                        actions.append("UP")
                    else:
                        actions.append("DOWN")
                    if delta > 0.05:    actions.append("L")
                    if delta < -0.05:   actions.append("R")
                    if max_trade > 0.1: actions.append("START")
                    if volatility > 25: actions.append("SELECT")

                    if actions:
                        # RANDOMIZE THE ORDER
                        random.shuffle(actions)

                        print(f"\n[{time.strftime('%H:%M:%S')}] Commands to Execute: {actions}")

                        # Feed the randomized list into the queue
                        for btn in actions:
                            await button_queue.put(btn)
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] No threshold met.")

                except Exception as e:
                    print(f"Logic Calculation Error: {e}")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] Quiet market.")

            batch = []
            last_batch_time = time.time()


async def gba_sender():
    """Pulls from button_queue and sends to mGBA with proper spacing."""
    while True:
        btn_name = await button_queue.get()
        char = BTN_MAP.get(btn_name)

        if char:
            try:
                # Open/Close connection per burst or keep persistent
                # Persistence is better for performance:
                reader, writer = await asyncio.open_connection(GBA_HOST, GBA_PORT)
                writer.write(f"{char}\n".encode())
                await writer.drain()
                writer.close()
                await writer.wait_closed()

                # Wait 0.2s: This gives the GBA 12 frames to process the
                # 6-frame press/release cycle we wrote in Lua.
                await asyncio.sleep(0.2)
            except Exception as e:
                print(f"Connection to mGBA failed: {e}")
                await asyncio.sleep(2)  # Wait before retrying

        button_queue.task_done()


async def main():
    print(f"Initializing Pokémon Market Controller on port {GBA_PORT}...")
    await asyncio.gather(
        get_coinbase_feed("BTC-USD"),
        gba_logic_mapper(),
        gba_sender()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSystem Offline.")

# --- Store Results ---

import sqlite3
from datetime import datetime, timedelta


def init_db():
    conn = sqlite3.connect('pokemon_market.db')
    cursor = conn.cursor()

    # Table 1: Raw logs (every single press)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS raw_moves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            button TEXT
        )
    ''')

    # Table 2: Daily Totals
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_aggregates (
            date TEXT PRIMARY KEY,
            button TEXT,
            press_count INTEGER
        )
    ''')
    conn.commit()
    conn.close()


def run_daily_aggregation():
    """Aggregates yesterday's moves and clears the raw log."""
    conn = sqlite3.connect('pokemon_market.db')
    cursor = conn.cursor()

    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        # 1. Get counts for each button
        cursor.execute('''
            SELECT button, COUNT(*) 
            FROM raw_moves 
            WHERE date(timestamp) = ?
            GROUP BY button
        ''', (yesterday,))

        results = cursor.fetchall()

        # 2. Insert into the aggregate table
        for button, count in results:
            cursor.execute('''
                INSERT OR REPLACE INTO daily_aggregates (date, button, press_count)
                VALUES (?, ?, ?)
            ''', (yesterday, button, count))

        # 3. Clean up: Delete raw logs older than 24 hours
        cursor.execute("DELETE FROM raw_moves WHERE timestamp < datetime('now', '-1 day')")

        conn.commit()
        print(f"[DATABASE] Aggregated {len(results)} buttons for {yesterday}")
    except Exception as e:
        print(f"[DATABASE] Aggregation Error: {e}")
    finally:
        conn.close()


async def daily_maintenance_loop():
    """Checks once an hour if it's midnight to run aggregation."""
    while True:
        now = datetime.now()
        # Trigger at 00:01 AM
        if now.hour == 0 and now.minute == 1:
            # Run the sync DB function in a thread
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, run_daily_aggregation)
            # Sleep for 70 seconds to ensure we don't trigger twice in the same minute
            await asyncio.sleep(70)

        await asyncio.sleep(60)  # Check every minute


def log_raw_move(btn):
    conn = sqlite3.connect('pokemon_market.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO raw_moves (button) VALUES (?)", (btn,))
    conn.commit()
    conn.close()

# Inside your async_log helper:
async def async_log(btn):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, log_raw_move, btn)