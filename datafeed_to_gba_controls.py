import asyncio
import json
import websockets
import time
import random
import os
from datetime import datetime

# --- Datafeed ---
GBA_HOST = "127.0.0.1"
GBA_PORT = 8888
BTN_MAP = {
    "A": "A", "B": "B", "START": "S", "SELECT": "s",
    "RIGHT": ">", "LEFT": "<", "UP": "^", "DOWN": "v",
    "L": "L", "R": "R"
}

# --- File Paths for OBS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LAST_10_FILE = os.path.join(BASE_DIR, "current_day_moves.txt")
TOTAL_AGG_FILE = os.path.join(BASE_DIR, "daily_total_moves.txt")

# --- Tracking Variables ---
last_10_list = []
total_counts = {k: 0 for k in BTN_MAP.keys()}
current_day = datetime.now().strftime('%Y-%m-%d')

# Shared Queues
trade_queue = asyncio.Queue()
button_queue = asyncio.Queue()


def check_day_rollover():
    """Checks if the date has changed. If so, archives totals and resets."""
    global current_day, total_counts, last_10_list

    today = datetime.now().strftime('%Y-%m-%d')

    if today != current_day:
        # 1. Format the aggregation row for the day that just ended
        sorted_btns = sorted(total_counts.items(), key=lambda x: x[0])
        # Format: 2026-01-01 | A:10, B:5, UP:20...
        counts_str = ", ".join([f"{k}:{v}" for k, v in sorted_btns if v > 0])
        archive_row = f"{current_day} | {counts_str if counts_str else 'No moves'}\n"

        # 2. Append to the aggregation file (History)
        with open(TOTAL_AGG_FILE, "a") as f:
            f.write(archive_row)

        # 3. Reset variables for the new day
        print(f"--- Day rolled over from {current_day} to {today}. Logs reset. ---")
        current_day = today
        last_10_list = []
        total_counts = {k: 0 for k in BTN_MAP.keys()}


def update_obs_files():
    """Writes tracking data to text files for OBS."""
    # Check for midnight rollover before writing
    check_day_rollover()

    # 1. Update Last 10 Moves (Vertical List) - Overwrites daily
    with open(LAST_10_FILE, "w") as f:
        f.write(f"RECENT MOVES ({current_day}):\n" + "\n".join(last_10_list))

    # Note: total_aggregations.txt is handled by check_day_rollover (Append mode)
    # If you also want to see a LIVE daily counter on screen,
    # you could create a third 'today_only.txt' file here.


async def get_coinbase_feed(symbol="BTC-USD"):
    url = "wss://ws-feed.exchange.coinbase.com"
    async with websockets.connect(url) as ws:
        subscribe = {"type": "subscribe", "product_ids": [symbol], "channels": ["ticker"]}
        await ws.send(json.dumps(subscribe))
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            if data.get("type") == "ticker":
                await trade_queue.put(data)


async def gba_logic_mapper():
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

        if time.time() - last_batch_time >= 2.0:
            if len(batch) > 0:
                try:
                    start_p, end_p = batch[0]["price"], batch[-1]["price"]
                    delta = ((end_p - start_p) / start_p) * 100
                    prices = [d["price"] for d in batch]
                    volatility = max(prices) - min(prices)
                    buys = len([d for d in batch if d["side"] == "buy"])
                    sells = len(batch) - buys
                    max_trade = max(d["size"] for d in batch)
                    trade_count = len(batch)

                    actions = []
                    if buys > sells:
                        actions.append("UP")
                        actions.append("UP")
                    if sells > buys:
                        actions.append("DOWN")
                        actions.append("DOWN")
                    if abs(delta) > 0.00005:       actions.append("B")
                    if abs(delta) <= 0.00005:      actions.append("A")
                    if trade_count >= 10:
                        actions.append("LEFT")
                        actions.append("LEFT")
                    else:
                        actions.append("RIGHT")
                        actions.append("RIGHT")
                    if delta > 0.05:    actions.append("L")
                    if delta < -0.05:   actions.append("R")
                    if max_trade > 0.1: actions.append("START")
                    if volatility > 25: actions.append("SELECT")

                    if actions:
                        random.shuffle(actions)
                        print(f"\n[{time.strftime('%H:%M:%S')}] Executing: {actions}")
                        for btn in actions:
                            await button_queue.put(btn)
                except Exception as e:
                    print(f"Logic Calculation Error: {e}")
            batch = []
            last_batch_time = time.time()


SAVE_INTERVAL = 3600  # 3600 seconds = 1 hour
last_save_time = time.time()


async def hourly_save_tracker():
    """Background task that triggers a save every hour."""
    global last_save_time
    while True:
        current_time = time.time()

        # Check if an hour has passed
        if current_time - last_save_time >= SAVE_INTERVAL:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Triggering Hourly Save...")

            # Put the special 'SAVE' command at the front of the queue
            await button_queue.put("SAVE")

            last_save_time = current_time

        # Sleep for a minute before checking the clock again
        await asyncio.sleep(60)

async def gba_sender():
    """Pulls from queue, updates logs, and sends to mGBA."""
    global last_10_list
    while True:
        btn_name = await button_queue.get()
        char = BTN_MAP.get(btn_name)

        if char:
            # --- Update Stats ---
            total_counts[btn_name] += 1
            last_10_list.append(btn_name)
            if len(last_10_list) > 10:
                last_10_list.pop(0)

            # --- Write to Files ---
            update_obs_files()

            # --- Send to mGBA ---
            try:
                reader, writer = await asyncio.open_connection(GBA_HOST, GBA_PORT)
                writer.write(f"{char}\n".encode())
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                await asyncio.sleep(0.2)
            except Exception as e:
                print(f"Connection to mGBA failed: {e}")
                await asyncio.sleep(2)

        button_queue.task_done()


async def main():
    # Initialize the Aggregation file with a header if it doesn't exist
    if not os.path.exists(TOTAL_AGG_FILE):
        with open(TOTAL_AGG_FILE, "w") as f:
            f.write("DATE | BUTTON PRESS TOTALS\n" + "=" * 30 + "\n")

    print(f"Initializing Pokémon Market Controller...")
    await asyncio.gather(
        get_coinbase_feed("BTC-USD"),
        gba_logic_mapper(),
        gba_sender(),
        hourly_save_tracker()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSystem Offline.")