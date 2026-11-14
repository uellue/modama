"""Shared helpers for the cache-tiling experiments: tokenizing, ONNX Runtime sessions, embedding, comparing.

Not run directly. Every script here expects the scratch folder TRIALS (default /var/tmp/embed-research-trials)
with models/fp32 (fp32.py convert of the pinned qdrant/bge-small-en-v1.5-onnx-q), models/onnx-q (the pinned
upstream), models/bge-small (BAAI/bge-small-en-v1.5 for PyTorch) and texts/*.jsonl (gen_texts.py).
"""

import json
import os
import statistics
import time
from pathlib import Path

import numpy as np

TRIALS = Path(os.environ.get("TRIALS", "/var/tmp/embed-research-trials"))
FP32 = TRIALS / "models/fp32/model_optimized.onnx"


def texts(name):
    with open(TRIALS / "texts" / name) as f:
        return [json.loads(line)["text"] for line in f]


def tokenizer(max_len=512):
    from tokenizers import Tokenizer

    tok = Tokenizer.from_file(str(TRIALS / "models/fp32/tokenizer.json"))
    tok.enable_truncation(max_len)
    return tok


def encode(tok, batch):
    """One padded batch as ONNX Runtime's int64 inputs."""
    enc = tok.encode_batch(batch)
    n = max(len(e.ids) for e in enc)
    ids = np.zeros((len(enc), n), np.int64)
    mask = np.zeros_like(ids)
    for i, e in enumerate(enc):
        ids[i, : len(e.ids)] = e.ids
        mask[i, : len(e.ids)] = 1
    return {
        "input_ids": ids,
        "attention_mask": mask,
        "token_type_ids": np.zeros_like(ids),
    }


def session(path=FP32, profile_prefix=None, opt_level=None, threads=1):
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.inter_op_num_threads = 1
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    if opt_level is not None:
        so.graph_optimization_level = opt_level
    if profile_prefix:
        so.enable_profiling = True
        so.profile_file_prefix = str(profile_prefix)
    return ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])


def sub_batches(order, n_tokens, sub_batch, tokens=None):
    """Consecutive groups of `order` (sorted by length): at most sub_batch texts and, with `tokens`, at most
    that many padded tokens (texts × the longest), always at least one text."""
    group, longest = [], 0
    for i in order:
        n = max(longest, n_tokens[i]) if tokens else 0
        if group and (
            len(group) == sub_batch or (tokens and (len(group) + 1) * n > tokens)
        ):
            yield group
            group, n = [], n_tokens[i] if tokens else 0
        group.append(i)
        longest = n
    if group:
        yield group


def embed(sess, tok, all_texts, sub_batch=32, tokens=None):
    """fastembed's way: in order of length, sub-batches, [CLS] vector, L2-normalized; given order back.
    The order is by characters, as patch 0002 sorts; `tokens` also bounds a sub-batch's padded tokens."""
    order = sorted(range(len(all_texts)), key=lambda i: len(all_texts[i]))
    n_tokens = [len(e.ids) for e in tok.encode_batch(all_texts)] if tokens else None
    out = np.zeros((len(all_texts), 384), np.float32)
    # a graph without a mask (ort_variants.py's mha-nomask) has fewer inputs
    names = {i.name for i in sess.get_inputs()} if hasattr(sess, "get_inputs") else None
    for idx in sub_batches(order, n_tokens, sub_batch, tokens):
        feed = encode(tok, [all_texts[i] for i in idx])
        h = sess.run(
            None, {k: v for k, v in feed.items() if names is None or k in names}
        )[0][:, 0]
        out[idx] = h / np.linalg.norm(h, axis=1, keepdims=True)
    return out


def compare(a, b):
    """(max abs difference, min cosine) over rows, in float64."""
    a = np.asarray(a, np.float64).reshape(len(a), -1)
    b = np.asarray(b, np.float64).reshape(len(b), -1)
    cos = (a * b).sum(1) / np.linalg.norm(a, axis=1) / np.linalg.norm(b, axis=1)
    return float(np.abs(a - b).max()), float(cos.min())


def median_time(fn, repeat=5, warmup=1):
    for _ in range(warmup):
        fn()
    ts = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t)
    return statistics.median(ts), ts
