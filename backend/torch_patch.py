import warnings
import logging
import sys
import io
import os
from contextlib import contextmanager
_patched = False

@contextmanager
def suppress_stdout():
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    
    _loggers_to_mute = [
        'accelerate', 'accelerate.utils', 'accelerate.utils.modeling',
        'accelerate.big_modeling', 'transformers', 'transformers.modeling_utils',
        'pyannote', 'pyannote.audio', 'pyannote.audio.core.model',
        'pytorch_lightning', 'lightning', 'lightning_fabric',
    ]
    _saved_levels = {}
    for name in _loggers_to_mute:
        _log = logging.getLogger(name)
        _saved_levels[name] = _log.level
        _log.setLevel(logging.CRITICAL)
    
    try:
        yield
    finally:
        sys.stdout = old_stdout
        for name, level in _saved_levels.items():
            logging.getLogger(name).setLevel(level)

def apply_torch_load_patch():
    global _patched
    
    if _patched:
        return
    
    import torch
    
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    
    _original_load = torch.load
    
    def _patched_load(*args, **kwargs):
        kwargs['weights_only'] = False
        return _original_load(*args, **kwargs)
    
    torch.load = _patched_load
    
    warnings.filterwarnings("ignore", message=".*Model was trained with pyannote.*")
    warnings.filterwarnings("ignore", message=".*Model was trained with torch.*")
    warnings.filterwarnings("ignore", message=".*Some weights of.*were not initialized.*")
    warnings.filterwarnings("ignore", message=".*Some weights of.*not used.*")
    warnings.filterwarnings("ignore", message=".*TensorFloat-32.*")
    warnings.filterwarnings("ignore", category=FutureWarning, module="transformers")
    warnings.filterwarnings("ignore", message=".*torchaudio.*deprecated.*")
    warnings.filterwarnings("ignore", message=".*torchaudio._backend.*")
    warnings.filterwarnings("ignore", message=".*ctranslate2.*")
    warnings.filterwarnings("ignore", message=".*layers were not sharded.*")
    warnings.filterwarnings("ignore", message=".*not sharded.*")
    warnings.filterwarnings("ignore", message=".*Lightning automatically upgraded.*")
    warnings.filterwarnings("ignore", message=".*lightning.*upgraded.*")
    warnings.filterwarnings("ignore", message=".*torchcodec.*")
    
    for logger_name in [
        "transformers.modeling_utils",
        "transformers.utils.hub",
        "transformers.generation.utils",
        "pyannote.audio",
        "pyannote.audio.core.model",
        "pyannote.core",
        "pytorch_lightning",
        "pytorch_lightning.utilities.migration",
        "lightning_fabric",
        "lightning",
        "speechbrain",
        "torchaudio",
        "whisperx",
        "accelerate",
        "accelerate.utils",
        "accelerate.big_modeling",
        "ctranslate2",
        "faster_whisper",
    ]:
        logging.getLogger(logger_name).setLevel(logging.ERROR)
    
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
    
    _patched = True