"""
LLM Access Layer - Centralized Ollama Interface
Nexira / Sygma - February 2026
Created by Xeeker & Claude

ALL Ollama calls go through this module. This ensures:
- ollama_url from config is always respected
- Hardware options (GPU, threads, context) are consistent
- Future enhancements (logging, retry, model routing) have one place to live
"""

import ollama
from typing import Dict, Optional


def get_client(config: Dict) -> ollama.Client:
    """
    Return an ollama.Client pointed at the configured ollama_url.
    Always use this instead of calling ollama.generate() directly.
    """
    url = config.get('ai', {}).get('ollama_url', 'http://localhost:11434')
    return ollama.Client(host=url)


def get_options(config: Dict) -> Dict:
    """
    Build Ollama runtime options from the hardware config.

    On Linux/NVIDIA: num_gpu=999 offloads all layers to CUDA.
    On Apple Silicon: num_gpu=999 offloads all layers to Metal.
    """
    hw = config.get('hardware', {})
    opts = {
        'num_ctx': hw.get('context_window', 16384),
        'num_thread': hw.get('num_threads', 4),
    }
    if hw.get('gpu_enabled', True) and hw.get('num_gpu', 1) > 0:
        opts['num_gpu'] = 999  # offload all layers to GPU
    else:
        opts['num_gpu'] = 0   # CPU only
    return opts


def generate(config: Dict, model: str, prompt: str,
             system: Optional[str] = None, **kwargs) -> Dict:
    """
    Generate a response from the configured Ollama instance.

    Args:
        config: The global config dict
        model: Model name (e.g. 'llama3.1:8b')
        prompt: The user/task prompt
        system: Optional system prompt
        **kwargs: Additional ollama.generate() parameters

    Returns:
        The raw ollama response dict (contains 'response' key)
    """
    client = get_client(config)
    options = get_options(config)

    call_kwargs = {
        'model': model,
        'prompt': prompt,
        'options': options,
    }
    if system:
        call_kwargs['system'] = system

    call_kwargs.update(kwargs)
    return client.generate(**call_kwargs)
