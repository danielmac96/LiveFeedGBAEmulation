import asyncio
import json
import websockets
import time
import socket

# Config
SYMBOL = "BTC-USD"
MGBA_ADDRESS = ("127.0.0.1", 8888)
trade_queue = asyncio.Queue()


async def get_coinbase_feed():
    url = "wss://ws-feed.exchange.coinbase.com"
    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({
            "type": "subscribe", "product_ids": [SYMBOL], "channels": ["ticker"]
        }))
        while True:
            msg = await ws.recv()
            await trade_queue.put(json.loads(msg))


def send_to_mgba(button_list):
    if not button_list:
        return

    message = ",".join(button_list)

    try:
        # We create a new connection for every batch to avoid "Broken Pipe" errors
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # Short timeout so it doesn't hang the whole script if mGBA is closed
            s.settimeout(0.5)
            s.connect(("127.0.0.1", 8888))
            s.sendall(message.encode())
            # mGBA likes a clean close
            s.shutdown(socket.SHUT_WR)
    except (ConnectionRefusedError, socket.timeout):
        print("Waiting for mGBA to respond...")


async def logic_mapper():
    batch = []
    last_batch_time = time.time()

    while True:
        try:
            data = await asyncio.wait_for(trade_queue.get(), timeout=1.0)
            if data.get("type") == "ticker":
                batch.append({"price": float(data["price"]), "side": data["side"]})
        except asyncio.TimeoutError:
            pass

        if time.time() - last_batch_time >= 5.0:
            active_buttons = []
            if batch:
                # Logic: If price went up since start of 5s, press A.
                # If more BUYS than SELLS, move RIGHT.
                change = batch[-1]["price"] - batch[0]["price"]
                buys = len([d for d in batch if d["side"] == "buy"])

                if change > 0: active_buttons.append("A")
                if change < 0: active_buttons.append("START")
                # if buys > (len(batch) / 2):
                #     active_buttons.append("RIGHT")
                else:
                    active_buttons.append("START")

                print(f"Batch ended. Sending: {active_buttons}")
                send_to_mgba(active_buttons)

            batch = []
            last_batch_time = time.time()


async def main():
    await asyncio.gather(get_coinbase_feed(), logic_mapper())


if __name__ == "__main__":
    asyncio.run(main())