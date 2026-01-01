import asyncio
import json
import websockets
import time
import random
import socket

# --- Configuration ---
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