import threading

import torch
import librosa as li
import numpy as np

from audio_descriptors.features import compute_all


class RaspFRAVE_Thread(threading.Thread):
    def __init__(self, model, audio_q, attr_mod, volume):
        threading.Thread.__init__(self, daemon=True)
        self.model = model
        self.attr_mod = attr_mod
        self.audio_q = audio_q
        self.attr_mod = attr_mod
        self.volume = volume

    @torch.no_grad()
    def run(self):
        buff = self.model.get_buffer(self.attr_mod, self.volume)
        self.audio_q.put(buff)


class RaspFRAVE():
    def __init__(self, modelpth, audiofile, blocksize, sr, bypass, modfile):
        self.blocksize = blocksize
        self.idx = 0

        self.model = torch.jit.load(modelpth)
        self.sr = sr

        audio, _ = li.load(audiofile, self.sr)
        audio = np.pad(audio, (0, blocksize - len(audio) % blocksize))
        self.audio_dur = audio.shape[0]
        self.nbuff = self.audio_dur // (self.blocksize)

        self.descriptors = [
            "centroid", "rms", "bandwidth", "sharpness", "booming"
        ]
        self.cached_phase = {}
        for descr in self.descriptors:
            self.cached_phase[descr] = 0

        self.latent = self.model.encode(
            torch.tensor(audio, requires_grad=False).reshape(1, 1, -1))
        self.fcomp = self.latent.shape[-1] / len(audio)

        self.feat = compute_all(audio,
                                sr=self.sr,
                                descriptors=self.descriptors,
                                resample=self.latent.shape[-1])
        self.feat = {descr: self.feat[descr] for descr in self.descriptors}
        self.feat = np.array(list(self.feat.values())).astype(np.float32)
        self.feat = torch.tensor(self.feat).unsqueeze(0)
        self.feat = self.model.normalize_all(self.feat)

        self.latent_batched = torch.zeros(
            (self.nbuff, self.latent.shape[1],
             self.latent.shape[-1] // self.nbuff))

        for j in range(len(self.latent[0, :, 0])):
            self.latent_batched[:, j] = self.latent[:, j].reshape(
                self.nbuff, -1)

        self.bypass = bypass
        self.load_modulator(modfile)
        self.source_modulator = {descr: False for descr in self.descriptors}

        self.select_mod()

    def modulate_attr(self, feat_buff, attr_mod, init_phase):
        for j, descr in enumerate(self.descriptors):
            feat = feat_buff[:, j].reshape(-1)
            t = torch.arange(len(feat))
            f = float(attr_mod[f"{descr}_lfo_speed"]) / 100
            a = float(attr_mod[f"{descr}_lfo_amplitude"]) / 100
            b = (float(attr_mod[f"{descr}_lfo_bias"]) / 100) - 0.5
            s = attr_mod[f"{descr}_lfo_waveform"]
            latent_sr = self.fcomp * self.sr

            if s == "sine":
                func = torch.sin

            elif s == "square":
                func = lambda x: torch.sign(torch.sin(x))

            elif s == "saw":
                func = lambda x: (2 / np.pi) * torch.arcsin(torch.sin(x))

            elif s == "noise":
                func = lambda x: torch.randn(x.shape)

            feat = feat * (
                1 + a * func(f * 20 * t / latent_sr + init_phase[descr])) + b
            self.cached_phase[
                descr] = f * 20 * t[-1] / latent_sr + init_phase[descr]

            feat_buff[:, j] = feat.reshape(feat_buff[:, j].shape)
        return feat_buff, init_phase

    def load_modulator(self, modfile):
        self.modfile = modfile
        y, _ = li.load(modfile, self.sr)
        y = np.pad(y, (0, self.blocksize - len(y) % self.blocksize))

        if y.shape[0] > self.audio_dur:
            y = y[:self.audio_dur]
        elif y.shape[0] < self.audio_dur:
            y = np.tile(y, 1 + self.audio_dur // len(y))[:self.audio_dur]

        self.external_feat = compute_all(y,
                                         sr=self.sr,
                                         descriptors=self.descriptors,
                                         resample=self.latent.shape[-1])
        self.external_feat = {
            descr: self.external_feat[descr]
            for descr in self.descriptors
        }
        self.external_feat = np.array(list(
            self.external_feat.values())).astype(np.float32)
        self.external_feat = torch.tensor(self.external_feat).unsqueeze(0)
        self.external_feat = self.model.normalize_all(self.external_feat)

    def change_volume(self, buff, vol):
        return buff * vol

    def select_mod(self):
        self.current_feat = self.feat.clone()
        print(self.source_modulator)
        for j, descr in enumerate(self.descriptors):
            if self.source_modulator[descr] == 'external':
                self.current_feat[:,
                                  j, :] = self.external_feat[:,
                                                             j, :].unsqueeze(0)
            elif self.source_modulator[descr] == 'none':
                self.current_feat[:, j, :] = -0.25*torch.ones_like(
                    self.current_feat[:, j, :])
                print("NTM")

        self.current_feat_batched = torch.zeros(
            (self.nbuff, self.current_feat.shape[1],
             self.current_feat.shape[-1] // self.nbuff))

        for j in range(len(self.descriptors)):
            self.current_feat_batched[:, j] = self.current_feat[:, j].reshape(
                self.nbuff, -1).clone()

    def get_full_attr(self, attr_mod):
        feat_mod, _ = self.modulate_attr(self.current_feat.clone(), attr_mod,
                                         self.cached_phase)
        for j, descr in enumerate(self.descriptors):
            if not self.bypass[descr]:
                feat_mod[:, j, :] = self.current_feat[:, j, :].clone()
                                
        return (feat_mod)

    def get_buffer(self, attr_mod=None, volume=1.):
        feat_buff = self.current_feat_batched[self.idx, ...].unsqueeze(0)
        latent_buff = self.latent_batched[self.idx, ...].unsqueeze(0)

        if attr_mod is not None:
            feat_mod, self.cached_phase = self.modulate_attr(
                feat_buff.clone(), attr_mod, self.cached_phase)

        else:
            feat_mod = feat_buff.clone()

        for j, descr in enumerate(self.descriptors):
            if not self.bypass[descr]:
                feat_mod[:, j, :] = feat_buff[:, j, :].clone()

        z = torch.cat((latent_buff, feat_mod), dim=1)
        buff = self.model.decode(z).squeeze().detach()
        self.idx = (self.idx + 1) % self.nbuff
        buff = self.change_volume(buff, volume)
        return buff
