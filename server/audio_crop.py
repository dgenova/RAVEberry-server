import librosa as li
import os
import soundfile as sf
import numpy as np

folders = os.listdir("./samples")

t = 8

for folder in folders:
    files = os.listdir("./samples/" + folder)
    j = 0
    for file in files:
        print(file)
        audio, sr = li.load(os.path.join("./samples/" + folder, file),
                            sr=44100)

        nb_samples = t * sr
        split = len(audio) // nb_samples + 1

        audios = np.array_split(audio, split)

        for audio in audios:
            sf.write(os.path.join("./samples/" + folder,
                                  str(j) + ".wav"),
                     audio,
                     samplerate=44100)
            j += 1
