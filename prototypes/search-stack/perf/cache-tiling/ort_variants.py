"""ONNX Runtime variants of bge-small-en-v1.5 for throughput.py, written to TRIALS/models/variants/.

From the repository root (common.py says what TRIALS holds):

  /var/tmp/embed-research-trials/venv/bin/python prototypes/search-stack/perf/cache-tiling/ort_variants.py

The float32 variants start from BAAI/bge-small-en-v1.5's own onnx/model.onnx, whose weights are bitwise the
pinned production file's (checked here), with ONNX Runtime's transformer optimizer (model_type bert, 12 heads,
hidden 384), the tanh GELU approximation (FastGelu, as the production file has) and no EmbedLayerNormalization
(as the production file):
  attn.onnx        the production file's operators (Attention with a mask index, FastGelu, SkipLayerNormalization)
  mha.onnx         MultiHeadAttention instead of Attention, with the attention mask
  mha-nomask.onnx  MultiHeadAttention without a mask: correct only for unpadded input (sub-batch 1, or texts
                   of equal length); ONNX Runtime's flash-attention kernel needs it
int8.onnx is quantize_dynamic of the float32 file (int8 weights, uint8 activations): CHANGES THE RESULTS.
"""

import common
import numpy as np
import onnx
from onnx import numpy_helper
from onnxruntime.quantization import QuantType, quantize_dynamic
from onnxruntime.transformers import optimizer
from onnxruntime.transformers.fusion_options import FusionOptions

SRC = common.TRIALS / "models/bge-small/onnx/model.onnx"
OUT = common.TRIALS / "models/variants"


def same_weights():
    base = {
        t.name: numpy_helper.to_array(t) for t in onnx.load(str(SRC)).graph.initializer
    }
    prod = {
        t.name: numpy_helper.to_array(t)
        for t in onnx.load(str(common.FP32)).graph.initializer
    }
    w = prod["Attention_0_qkv_weight"]
    hits = [
        n
        for n, a in base.items()
        if a.shape == (384, 384) and np.array_equal(a, w[:, :384])
    ]
    emb = np.array_equal(
        base["embeddings.word_embeddings.weight"],
        prod["embeddings.word_embeddings.weight"],
    )
    print(
        f"layer 0 query weight found bitwise in the source: {hits}; word embeddings equal: {emb}"
    )


def make(name, mha=False, nomask=False):
    o = FusionOptions("bert")
    o.enable_gelu_approximation = True
    o.enable_embed_layer_norm = False
    o.use_multi_head_attention = mha
    if nomask:
        o.disable_attention_mask()
    m = optimizer.optimize_model(
        str(SRC),
        "bert",
        num_heads=12,
        hidden_size=384,
        optimization_options=o,
        opt_level=0,
    )
    m.save_model_to_file(str(OUT / name), use_external_data_format=False)
    print(name, m.get_fused_operator_statistics())


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    same_weights()
    for name, kw in [
        ("attn.onnx", {}),
        ("mha.onnx", {"mha": True}),
        ("mha-nomask.onnx", {"mha": True, "nomask": True}),
    ]:
        if not (OUT / name).exists():
            make(name, **kw)
    quantize_dynamic(
        str(common.FP32),
        str(OUT / "int8.onnx"),
        weight_type=QuantType.QInt8,
        extra_options={"DefaultTensorType": onnx.TensorProto.FLOAT},
    )
    print("int8.onnx written (changes the results)")
