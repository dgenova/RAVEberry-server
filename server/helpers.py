from pydantic import BaseSettings, Field, BaseModel, validator


class Config(BaseModel):
    sr: int = 48000
    n_signal: int = 65536
    preprocessed: str = None
    wav: str = None
    descriptors: list = []
    data_name: str = None
    r_samples: float = None
    nb_bins: int = 16