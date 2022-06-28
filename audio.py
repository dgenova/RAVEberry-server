import threading

import numpy as np
import sounddevice as sd
import librosa as li

from realtimeFRAVE import RaspFRAVE_Thread

class Audio(threading.Thread):
    def __init__(self, model, sr, blocksize, queue, attr_mod, volume, playing):
        self.sr = sr
        self.blocksize = blocksize
        threading.Thread.__init__(self, daemon=True)
        sd.default.samplerate = sr
        sd.default.blocksize = blocksize
        sd.default.device = 3

        self.audio_q = queue
        self.audio_q.put(np.zeros(self.blocksize))
        self.cur_stream = None
        self.model = model
        self.model_thread = None
        self.playing = playing

        self.attr_mod = attr_mod
        self.volume = volume

    def __del__(self):
        if self.cur_stream is not None:
            self.cur_stream.close()

    def model_callback(self):
        self.model_thread = RaspFRAVE_Thread(self.model, self.audio_q,
                                             self.attr_mod, self.volume)
        self.model_thread.daemon = True
        self.model_thread.start()
        

    def run(self):
        def callback(outdata, frames, times, status):
            curdata = self.audio_q.get()

            if curdata is None or not self.playing:
                print("empty queue or stopped")
                if self.model_thread is not None and self.model_thread.is_alive(
                ):
                    self.model_thread.join()
                self.cur_stream.close()
                raise sd.CallbackStop()

            outdata[:] = curdata[:, np.newaxis]
            self.model_callback()

        if self.cur_stream is None:
            print('Starting audio stream')
            self.cur_stream = sd.OutputStream(callback=callback,
                                              blocksize=self.blocksize,
                                              channels=1)
            self.cur_stream.start()
            print('Stream started')

        elif not self.cur_stream.active:
            self.cur_stream.close()
            self.cur_stream = sd.OutputStream(callback=callback,
                                              blocksize=self.blocksize,
                                              channels=1)
            self.cur_stream.start()
            
class SampleAudio(threading.Thread):
    def __init__(self, audiofile, sr, blocksize, queue, volume, playing, idx=0):
        self.sr = sr
        self.blocksize = blocksize
        threading.Thread.__init__(self, daemon=True)
        sd.default.samplerate = sr
        sd.default.blocksize = blocksize
        sd.default.device = 3

        self.volume = volume
        self.audio, _ = li.load(audiofile, self.sr)
        self.audio = np.pad(self.audio, (0, blocksize - len(self.audio) % blocksize))
        self.nbuff = self.audio.shape[0] // (self.blocksize)
        self.audio = self.audio.reshape(self.nbuff, -1)
        self.idx = idx
        
        self.audio_q = queue
        self.audio_q.put(self.audio[self.idx,...])
        self.cur_stream = None
        self.playing = playing

    def __del__(self):
        if self.cur_stream is not None:
            self.cur_stream.close()
    
    def audio_callback(self) :
        audio_buff = self.audio[self.idx+1]*self.volume
        self.audio_q.put(audio_buff)
        self.idx = (self.idx+1)%self.nbuff     

    def run(self):
        def callback(outdata, frames, times, status):
            curdata = self.audio_q.get()

            if curdata is None or not self.playing:
                print("empty queue or stopped")
                self.cur_stream.close()
                raise sd.CallbackStop()

            else :
                outdata[:] = curdata[:, np.newaxis]
                self.audio_callback()

        if self.cur_stream is None:
            print('Starting audio stream')
            self.cur_stream = sd.OutputStream(callback=callback,
                                              blocksize=self.blocksize,
                                              channels=1)
            self.cur_stream.start()
            print('Stream started')

        elif not self.cur_stream.active:
            self.cur_stream.close()
            self.cur_stream = sd.OutputStream(callback=callback,
                                              blocksize=self.blocksize,
                                              channels=1)
            self.cur_stream.start()