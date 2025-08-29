# services/common/kg_common/llm.py
import os
from typing import Any, Dict, List
from llama_cpp import Llama, LlamaGrammar  # noqa: F401  (grammar not used, but kept for future)
import threading

# Env-tunable, with conservative CPU defaults
MODEL_PATH = os.getenv("MODEL_PATH", "/models/qwen2.5-1.5b-instruct-q4_k_m.gguf")
N_CTX      = int(os.getenv("N_CTX", "2048"))
N_THREADS  = int(os.getenv("N_THREADS", "4"))
N_BATCH    = int(os.getenv("N_BATCH", "24"))   # keep small on CPU
CHAT_FMT   = os.getenv("CHAT_FORMAT", "qwen")  # llama_cpp chat handler name

_llm_lock = threading.Lock()
_llm: Llama | None = None

def _get_llm() -> Llama:
    global _llm
    if _llm is not None:
        return _llm
    if not os.path.isfile(MODEL_PATH):
        raise ValueError(f"Model not found: {MODEL_PATH}")
    with _llm_lock:
        if _llm is None:
            _llm = Llama(
                model_path=MODEL_PATH,
                n_ctx=N_CTX,
                n_threads=N_THREADS,
                n_batch=N_BATCH,
                use_mmap=True,
                use_mlock=False,
                logits_all=False,   # avoid heavy logits buffer on CPU
                chat_format=CHAT_FMT,
                verbose=False,
            )
    return _llm

def complete(system: str, user: str, max_tokens: int = 128, temperature: float = 0.2) -> str:
    """
    Chat-style completion using llama.cpp chat handlers.
    """
    llm = _get_llm()
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]
    # Create a single, non-streaming chat completion
    res: Dict[str, Any] = llm.create_chat_completion(
        messages=messages,
        temperature=float(temperature),
        max_tokens=int(max_tokens),
        top_p=0.95,
        repeat_penalty=1.05,
    )
    try:
        return res["choices"][0]["message"]["content"].strip()
    except Exception:
        return str(res)

def embed(text: str) -> List[float]:
    """
    Cheap embedding: reuse the LLM logits over a short prompt to produce a vector.
    For production, swap in a real text-embedding model and return list[float].
    """
    # Minimal, fast, CPU-friendly trick embedding:
    # feed a short prefix and use final_state embedding if available
    # Fallback to a deterministic vector based on bytes.
    try:
        llm = _get_llm()
        out = llm.embed(text[:1000])  # llama.cpp provides .embed() in newer versions
        if isinstance(out, list) and out and isinstance(out[0], (float, int)):
            return [float(x) for x in out]
    except Exception:
        pass
    # Fallback dummy embedding (still works with Qdrant end-to-end)
    import math
    h = [0.0] * 256
    for i, b in enumerate(text.encode("utf-8", errors="ignore")):
        h[i % 256] += (b / 255.0)
    # l2 normalize
    n = math.sqrt(sum(x * x for x in h)) or 1.0
    return [x / n for x in h]
