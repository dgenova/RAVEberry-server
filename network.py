import threading
import asyncio
import json

import websockets


class Network(threading.Thread):
    def __init__(self, rx_queue, tx_queue, ip="", port=8001):
        super(Network, self).__init__()
        self.rx_queue = rx_queue
        self.tx_queue = tx_queue
        self.ip = ip
        self.port = port
        self.new_connection = False

    def run(self):
        asyncio.run(self.do_turn())

    async def do_turn(self):
        async with websockets.serve(self.handler, self.ip, self.port):
            await asyncio.Future()  # run forever

    async def consumer_handler(self, websocket):
        self.new_connection = True
        while True:
            async for message in websocket:
                self.rx_queue.put(json.loads(message))

    async def producer_handler(self, websocket):
        while True:
            await websocket.send(json.dumps(self.tx_queue.get()))
            await asyncio.sleep(0.01)

    async def handler(self, websocket):
        rx_task = asyncio.ensure_future(self.consumer_handler(websocket))
        tx_task = asyncio.ensure_future(self.producer_handler(websocket))
        done, pending = await asyncio.wait(
            [rx_task, tx_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            print("han2")
            task.cancel()