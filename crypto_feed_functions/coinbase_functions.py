import asyncio
import json
import websockets
import time
from collections import deque

# Global Queue to share data between functions
trade_queue = asyncio.Queue()

async def get_coinbase_feed(symbol="BTC-USD"):
    """Fetch live trades and put them in a queue."""
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
    batch = []
    last_batch_time = time.time()

    while True:
        try:
            # Collect data from queue
            data = await asyncio.wait_for(trade_queue.get(), timeout=1.0)
            batch.append({
                "price": float(data["price"]),
                "size": float(data.get("last_size", 0)),
                "side": data.get("side")
            })
        except asyncio.TimeoutError:
            pass

        if time.time() - last_batch_time >= 5.0:
            active_buttons = []
            if batch:
                # --- Metrics Calculation ---
                start_p, end_p = batch[0]["price"], batch[-1]["price"]
                delta = ((end_p - start_p) / start_p) * 100
                volatility = max(d["price"] for d in batch) - min(d["price"] for d in batch)
                buys = len([d for d in batch if d["side"] == "buy"])
                sells = len(batch) - buys
                max_trade = max(d["size"] for d in batch)

                # --- 10-Channel Evaluation ---
                if buys > sells:      active_buttons.append("RIGHT")
                if sells > buys:     active_buttons.append("LEFT")
                if delta > 0.02:      active_buttons.append("A")
                if delta < -0.02:     active_buttons.append("B")
                if max_trade > 0.1:   active_buttons.append("START")
                if volatility > 10:   active_buttons.append("SELECT")
                if delta > 0.1:       active_buttons.append("UP")
                if delta < -0.1:      active_buttons.append("DOWN")
                if len(batch) > 50:   active_buttons.append("L")  # High activity
                if len(batch) < 5:    active_buttons.append("R")  # Low activity

                print(f"[{time.strftime('%H:%M:%S')}] Active Buttons: {active_buttons}")
                # TODO: Phase 3 - Send 'active_buttons' list to Database/Emulator

            batch = []
            last_batch_time = time.time()

async def main():
    print("Initializing Pokémon Market Controller...")
    await asyncio.gather(
        get_coinbase_feed("BTC-USD"),
        gba_logic_mapper()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("System Offline.")