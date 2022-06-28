import signal
import queue
import time
import os
import glob
import sys

import torch
import numpy as np

from audio import Audio, SampleAudio
from network import Network
from realtimeFRAVE import RaspFRAVE

torch.set_grad_enabled(False)


def get_files_in_folder(dir_path, extension):
    res = []
    for file in os.listdir(dir_path):
        if file.endswith(extension):
            res.append(file)
    return res


class RaspiRave(object):
    def __init__(self):
        super(RaspiRave, self).__init__()
        # State
        self.descriptors = [
            "centroid", "rms", "bandwidth", "sharpness", "booming"
        ]

        self.blocksize_model = 8192

        self.sr = 44100
        self.audio_q = queue.Queue(10)
        self.playing = False
        self.playing_sample = False
        self.sample_idx_1 = 0
        self.sample_idx_2 = 0

        self.attr_mod = {}
        self.volume = 1.
        self.bypass = {descr: False for descr in self.descriptors}

    def get_attr_mod(self):
        for state, value in self.state.items():
            if 'lfo' in state:
                self.attr_mod[state] = value

    def reset_attr(self, attr):
        for state in self.state.keys():
            if attr in state:
                if 'speed' in state:
                    self.attr_mod[state] = 1.0
                elif 'amplitude' in state:
                    self.attr_mod[state] = 0.
                elif 'bias' in state:
                    self.attr_mod[state] = 0.
                elif 'waveform' in state:
                    self.attr_mod[state] = 'sine'
        print(f'Attribute {attr} reset to default')

    def load_model(self, modelpth, audiofile, modfile):
        model = RaspFRAVE(modelpth, audiofile, self.blocksize_model, self.sr,
                          self.bypass, modfile)
        self.blocksize = model.get_buffer().shape[0]
        self.get_attr_mod()
        feat = model.get_full_attr(self.attr_mod)
        for j, descr in enumerate(model.descriptors):
            self.update_plot(feat, model, descr)
        return model

    def start_playing(self, model):
        self.audio_thread = Audio(model, self.sr, self.blocksize, self.audio_q,
                                  self.attr_mod, self.volume, self.playing)
        self.audio_thread.daemon = True
        self.audio_thread.start()

    def start_playing_sample(self, audiofile, idx):
        self.sample_thread = SampleAudio(audiofile, self.sr, self.blocksize,
                                         self.audio_q, self.volume,
                                         self.playing_sample, idx)
        self.sample_thread.daemon = True
        self.sample_thread.start()

    def update_plot(self, feat, model, descr):
        j = model.descriptors.index(descr)
        self.tx.put({
            "msg_type": "graph",
            "descriptor": descr,
            "data": feat[:, j, :].squeeze().tolist()
        })

    def init_network(self):

        self.states = {
            "lfo_speed": 50,
            "lfo_amplitude": 50,
            "lfo_bias": 50,
            "lfo_waveform": "sine",
            "modulation_activated": False,
            "input_source": None
        }

        self.modelspath = "./models"
        self.audiopath = "./samples"

        self.available_models = get_files_in_folder(self.modelspath, ".ts")
        self.audio_samples_categories = next(os.walk(self.audiopath))[1]
        self.available_audio_samples = {}
        for c in self.audio_samples_categories:
            self.available_audio_samples[c] = get_files_in_folder(
                os.path.join(self.audiopath, c), ".wav")

        first_audio_sample = os.path.join(
            self.audio_samples_categories[0],
            self.available_audio_samples[self.audio_samples_categories[0]][0])

        self.state = {
            "model": self.available_models[0],
            "original_sample": first_audio_sample,
            "external_sample": first_audio_sample,
            "output_volume": 1.0,
            "play": True,
            "play_sample": 'original',
        }

        for descriptor in self.descriptors:
            for state, value in self.states.items():
                self.state[f"{descriptor}_{state}"] = value

        # Network thread
        signal.signal(signal.SIGINT, self.signal_handler)
        self.rx = queue.Queue()
        self.tx = queue.Queue()
        self.network_thread = None
        self.network_thread = Network(self.rx, self.tx)
        self.network_thread.daemon = True

    def signal_handler(self, signum, frame):
        # Needed to close the other thread
        self.rx.put(None)
        self.tx.put(None)
        exit(1)

    def launch(self):
        self.init_network()
        self.network_thread.start()

        modelpth = os.path.join(self.modelspath, self.state["model"])
        audio_sample = os.path.join(self.audiopath,
                                    self.state["original_sample"])
        modulator_sample = os.path.join(self.audiopath,
                                        self.state["original_sample"])
        model = self.load_model(modelpth, audio_sample, modulator_sample)
        must_load_model = False

        while True:

            if self.network_thread.new_connection:
                self.tx.put("New Connection")
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
                print(msg)

                if msg["type"] in self.state.keys():
                    print(
                        f"{msg['type']} changed from {self.state[msg['type']]}",
                        end='')
                    self.state[msg["type"]] = msg["state"]
                    print(f" to {self.state[msg['type']]}")
                else:
                    print(f"Unknown key: {msg}")
                self.get_attr_mod()

                if msg["type"] == "play":
                    try:
                        self.sample_thread.playing = False
                        self.sample_idx_1 = 0
                        self.sample_idx_2 = 0
                    except:
                        pass
                    self.playing_sample = False
                    if (not self.playing) and msg["state"]:
                        self.tx.put("Start Playing")
                        self.playing = True
                        self.start_playing(model)

                    elif not msg["state"]:
                        self.tx.put("Pause")
                        self.audio_thread.playing = False
                        self.playing = False

                elif msg["type"] == "model" or 'sample' in msg[
                        "type"] and msg["type"] != "play_sample":

                    must_load_model = True

                elif msg["type"] == "output_volume":
                    self.volume = -0.01 + int(
                        self.state["output_volume"]) / 100
                    self.audio_thread.volume = self.volume

                elif 'modulation_activated' in msg["type"]:
                    descr_name = msg["type"].split('_')[0]
                    self.bypass[descr_name] = self.state[msg["type"]]
                    model.bypass = self.bypass
                    model.select_mod()

                elif 'input_source' in msg["type"]:
                    descr = msg["type"].split('_')[0]
                    model.source_modulator[descr] = self.state[msg["type"]]
                    model.select_mod()

                elif 'play_sample' in msg["type"]:
                    try:
                        self.audio_thread.playing = False
                        self.playing = False
                    except:
                        pass
                    if not self.playing_sample:
                        if self.state[msg["type"]] == 'original':
                            self.start_playing_sample(audio_sample,
                                                      self.sample_idx_1)
                            self.tx.put("Start Playing Original Sample")
                            use_ori = True
                            use_ext = False
                        elif self.state[msg["type"]] == 'external':
                            self.start_playing_sample(modulator_sample,
                                                      self.sample_idx_2)
                            self.tx.put("Start Playing External Sample")
                            use_ori = False
                            use_ext = True
                        self.sample_thread.playing = True
                    else:
                        if use_ori:
                            self.sample_idx_1 = self.sample_thread.idx
                        elif use_ext:
                            self.sample_idx_2 = self.sample_thread.idx
                        self.sample_thread.playing = False
                        self.tx.put("Paused Sample")
                    self.playing_sample = not self.playing_sample

                for descr in model.descriptors:
                    if descr in msg["type"]:
                        feat = model.get_full_attr(self.attr_mod)
                        self.update_plot(feat, model, descr)

            if must_load_model:
                self.tx.put("Loading Model and Samples ... ")
                self.playing = False
                try:
                    self.audio_thread.playing = False
                except:
                    pass

                audio_sample = glob.glob(self.audiopath + "/**/" +
                                         self.state["original_sample"],
                                         recursive=True)[0]

                modulator_sample = glob.glob(self.audiopath + "/**/" +
                                             self.state["external_sample"],
                                             recursive=True)[0]

                model = self.load_model(
                    os.path.join(self.modelspath, self.state["model"]),
                    audio_sample, modulator_sample)
                print('Model loaded')
                self.playing = True
                self.start_playing(model)
                must_load_model = False
                self.tx.put("Model Loaded")

            time.sleep(0.01)

            self.tx.put({"msg_type": "none"})


if __name__ == "__main__":
    try:
        app = RaspiRave()
        app.launch()
    except KeyboardInterrupt:
        print('Interruption')
        sys.exit()