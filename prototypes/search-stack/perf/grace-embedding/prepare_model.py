"""Model files of our own for the benchmark's variants, made once from the model fastembed
loads (qdrant/bge-small-en-v1.5-onnx-q at bench.py's MODEL_REVISION, model_optimized.onnx),
into CACHE/variants/:

  model-fp32.onnx (+ model-fp32.onnx.data)
      The same graph with every float16 tensor stored as float32: the weights as
      external data, which ONNX Runtime maps into memory (1.24.4,
      core/framework/tensorprotoutils.cc, GetFileContent: map first, copy only if that
      fails), so that processes can share the pages. The production file stores the
      weights in float16; on the CPU, ONNX Runtime casts them to float32 on every run.
      On the GPU the production file computes in float16, this one in float32.
  model-int8.onnx
      Dynamic int8 quantisation of model-fp32 (onnxruntime.quantization), for
      information only: it changes every vector.

  python prepare_model.py   (the venv-cpu Python; needs the onnx package)

Does nothing for a file that already exists. CACHE is FASTEMBED_CACHE_DIR or ./cache.
"""

import sys
from pathlib import Path

# the pinned model files, the cache directories (bench.py sets them on import)
from bench import VARIANTS as OUT
from bench import model_dir


def source() -> Path:
    return Path(model_dir()) / "model_optimized.onnx"


def to_fp32(src: Path, dst: Path) -> None:
    import numpy as np
    import onnx
    from onnx import TensorProto, numpy_helper

    m = onnx.load(str(src))
    n = 0
    for i, t in enumerate(m.graph.initializer):
        if t.data_type == TensorProto.FLOAT16:
            a = numpy_helper.to_array(t).astype(np.float32)
            m.graph.initializer[i].CopyFrom(numpy_helper.from_array(a, t.name))
            n += 1
    for node in m.graph.node:
        for attr in node.attribute:
            if node.op_type == "Constant" and attr.t.data_type == TensorProto.FLOAT16:
                a = numpy_helper.to_array(attr.t).astype(np.float32)
                attr.t.CopyFrom(numpy_helper.from_array(a, attr.t.name))
            if (
                node.op_type == "Cast"
                and attr.name == "to"
                and attr.i == TensorProto.FLOAT16
            ):
                attr.i = TensorProto.FLOAT
    for v in [*m.graph.input, *m.graph.output]:
        if v.type.tensor_type.elem_type == TensorProto.FLOAT16:
            v.type.tensor_type.elem_type = TensorProto.FLOAT
    del m.graph.value_info[:]  # the shape inference's types, float16 ones among them
    # no onnx.checker: the file uses LayerNormalization at opset 11, as ONNX Runtime
    # accepts and the checker does not; the benchmark checks the vectors instead
    onnx.save_model(
        m,
        str(dst),
        save_as_external_data=True,
        all_tensors_to_one_file=True,
        location=dst.name + ".data",
        size_threshold=1024,
    )
    print(f"{dst}: {n} float16 initializers as float32, external data", file=sys.stderr)


def to_int8(src: Path, dst: Path) -> None:
    from onnx import TensorProto
    from onnxruntime.quantization import QuantType, quantize_dynamic

    # the shape inference does not know the contrib operators' output types
    extra = {"DefaultTensorType": TensorProto.FLOAT}
    quantize_dynamic(
        str(src), str(dst), weight_type=QuantType.QInt8, extra_options=extra
    )
    print(f"{dst}: dynamic int8 quantisation", file=sys.stderr)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fp32, int8 = OUT / "model-fp32.onnx", OUT / "model-int8.onnx"
    if not fp32.exists():
        to_fp32(source(), fp32)
    if not int8.exists():
        to_int8(fp32, int8)


if __name__ == "__main__":
    main()
