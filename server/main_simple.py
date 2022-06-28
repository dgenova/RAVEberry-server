# https://websockets.readthedocs.io/en/5.0/intro.html#both
# https://www.solasistim.net/posts/websocket_server/
# https://javascript.info/websocket
import websockets
import threading
import asyncio
import random
import signal
import queue
import time
import json
import os


def get_files_in_folder(dir_path, extension):
    res = []
    for file in os.listdir(dir_path):
        if file.endswith(extension):
            res.append(file)
    return res


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
            await asyncio.sleep(0.1)

    async def handler(self, websocket):
        rx_task = asyncio.ensure_future(
            self.consumer_handler(websocket)
        )
        tx_task = asyncio.ensure_future(
            self.producer_handler(websocket)
        )
        done, pending = await asyncio.wait(
            [rx_task, tx_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            print("han2")
            task.cancel()


class RaspiRave(object):
    def __init__(self):
        super(RaspiRave, self).__init__()
        # State
        self.descriptors = ["centroid", "rms",
                            "bandwidth", "sharpness", "boominess"]
        self.states = {
            "lfo_speed": 1.0,
            "lfo_amplitude": 1.0,
            "lfo_bias": 0.0,
            "lfo_shape": "sine"
        }
        self.available_models = get_files_in_folder("./models/", ".ts")
        self.audio_samples_categories = next(os.walk("./audio_samples/"))[1]
        self.available_audio_samples = {}
        for c in self.audio_samples_categories:
            self.available_audio_samples[c] = get_files_in_folder(
                os.path.join("./audio_samples/", c),
                ".wav"
            )
        first_audio_sample = self.available_audio_samples[self.audio_samples_categories[0]],
        self.state = {
            "model": self.available_models[0],
            "audio_sample": first_audio_sample,
            "output_volume": 1.0,
            "play": True
        }
        for descriptor in self.descriptors:
            for state, value in self.states.items():
                self.state[f"{descriptor}_{state}"] = value
        # Network thread
        self.rx = queue.Queue()
        self.tx = queue.Queue()
        self.network_thread = None
        self.network_thread = Network(self.rx, self.tx)
        self.network_thread.daemon = True

    def launch(self):
        self.network_thread.start()

        while True:
            if self.network_thread.new_connection:
                self.tx.put({
                    "msg_type": "models_audio_samples_info",
                    "models": self.available_models,
                    "audio_samples": self.available_audio_samples
                })
                self.network_thread.new_connection = False

            if self.rx.empty():
                pass
            tmp_buffer = []
            while not self.rx.empty():
                tmp_buffer.append(self.rx.get())
            for msg in tmp_buffer:
                if msg["type"] in self.state:
                    print(
                        f"{msg['type']} changed from {self.state[msg['type']]}", end='')
                    self.state[msg["type"]] = msg["state"]
                    print(f" to {self.state[msg['type']]}")
                else:
                    print(f"Unknown key: {msg}")

            # Now get the model's prediction
            time.sleep(2)
            descs = ["centroid", "rms", "bandwidth", "sharpness", "booming"]
            self.tx.put({"msg_type": "graph", "descriptor": random.choice(descs),
                        "data": [random.randint(-100, 100) / 100 for i in range(25)]})


if __name__ == "__main__":
    app = RaspiRave()
    app.launch()
