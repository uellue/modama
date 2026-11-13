"""The warehouse's embedding model stored in float32, made at image build (change embedding-fp32-model,
python/crawler/openspec/changes/embedding-fp32-model/; spec embedding-model).

  python fp32.py convert UPSTREAM OUT
      UPSTREAM holds the five pinned files of qdrant/bge-small-en-v1.5-onnx-q (PINS). Writes OUT with the
      same graph, every float16 tensor stored as float32 and the weights in model_optimized.onnx.data,
      the four tokenizer and configuration files, and the marker modama-model.json; every file 0644, the
      folder 0755 (onnx writes the weight file 0600). Needs the onnx package.

  python fp32.py check UPSTREAM OUT NAME=TEXTS...
      Embeds each set of texts (JSON lines with a "text", as perf/grace-embedding/gen_texts.py writes
      them) with both folders as the transform batches do (fastembed, one thread, in order of length,
      sub-batches of 32) and reports per set the bitwise-identical count,
      the largest component difference and the minimum cosine (float64). Exits 1 when a cosine is below
      MIN_COSINE or when the installed fastembed describes the marker's model with another source or file.
      Needs fastembed (the image's transform venv).

The float32 conversion is perf/grace-embedding/prepare_model.py's to_fp32 (the grace benchmark measured
that file); test_fp32.py checks that both write the same bytes.
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

MODEL = "BAAI/bge-small-en-v1.5"
SOURCE = "qdrant/bge-small-en-v1.5-onnx-q"
REVISION = "aa8f8b060edb00e03bfdd08813a2949946c8ba55"
MODEL_FILE = "model_optimized.onnx"
# the upstream files at REVISION; warehouse-airflow.Dockerfile fetches them with these hashes
PINS = {
    MODEL_FILE: "51f1bd0addd6e859e42c2c8021a5e5461385bb676a649f4b269aa445449f2431",
    "tokenizer.json": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
    "tokenizer_config.json": "0b29c7bfc889e53b36d9dd3e686dd4300f6525110eaa98c76a5dafceb2029f53",
    "special_tokens_map.json": "5d5b662e421ea9fac075174bb0688ee0d9431699900b90662acd44b2a350503a",
    "config.json": "13582bcf2effc85b7bf3d3f5532e686bc1c9ce86bb009d10f0ec33cbe92299dd",
}
MARKER = (
    "modama-model.json"  # read by patch 0004, which refuses a folder of another model
)
MIN_COSINE = 0.99999  # design D4: measured 0.99999963; the int8 file gives 0.9647
SUB_BATCH = 32  # patch 0002's


def convert(upstream: Path, out: Path) -> None:
    import onnx
    from onnx import TensorProto, numpy_helper

    out.mkdir(parents=True)
    m = onnx.load(str(upstream / MODEL_FILE))
    for i, t in enumerate(m.graph.initializer):
        if t.data_type == TensorProto.FLOAT16:
            a = numpy_helper.to_array(t).astype("float32")
            m.graph.initializer[i].CopyFrom(numpy_helper.from_array(a, t.name))
    for node in m.graph.node:
        for attr in node.attribute:
            if node.op_type == "Constant" and attr.t.data_type == TensorProto.FLOAT16:
                a = numpy_helper.to_array(attr.t).astype("float32")
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
    # no onnx.checker: LayerNormalization at opset 11, which ONNX Runtime accepts and the checker does not;
    # the check command compares the vectors instead
    onnx.save_model(
        m,
        str(out / MODEL_FILE),
        save_as_external_data=True,
        all_tensors_to_one_file=True,
        location=MODEL_FILE + ".data",
        size_threshold=1024,
    )
    for name in PINS:
        if name != MODEL_FILE:
            shutil.copyfile(upstream / name, out / name)
    marker = {
        "model": MODEL,
        "source": SOURCE,
        "revision": REVISION,
        "model_file": MODEL_FILE,
        "upstream_sha256": PINS,
        "conversion": "every float16 tensor stored as float32 (change embedding-fp32-model)",
        "onnx": onnx.__version__,
    }
    (out / MARKER).write_text(json.dumps(marker, indent=2) + "\n")
    os.chmod(out, 0o755)
    for p in out.iterdir():
        os.chmod(p, 0o644)
    print(
        f"{out}: float32 graph of {SOURCE}@{REVISION[:12]}, onnx {onnx.__version__}",
        file=sys.stderr,
    )


def description_mismatch(marker: dict, descriptions) -> str | None:
    """Why the installed fastembed's description of the marker's model does not fit the pinned files."""
    found = [d for d in descriptions if d.model.lower() == marker["model"].lower()]
    if not found:
        return f"fastembed does not know {marker['model']}"
    d = found[0]
    if (d.sources.hf, d.model_file) != (marker["source"], marker["model_file"]):
        return (
            f"fastembed describes {marker['model']} as {d.sources.hf}, {d.model_file}; "
            f"the pinned files are {marker['source']}, {marker['model_file']}: re-pin "
            "(prototypes/search-stack/README.md, Upgrade)"
        )
    return None


def check(upstream: Path, out: Path, sets: dict[str, Path]) -> int:
    import numpy as np
    from fastembed import TextEmbedding

    marker = json.loads((out / MARKER).read_text())
    problem = description_mismatch(marker, TextEmbedding._list_supported_models())
    if problem:
        print(f"check: {problem}", file=sys.stderr)
        return 1

    def embed(folder: Path, texts: list[str]) -> "np.ndarray":
        # as patch 0002 embeds a batch: in order of length, sub-batches of 32, back in the given order
        model = TextEmbedding(
            marker["model"], specific_model_path=str(folder), threads=1
        )
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        got = list(model.embed([texts[i] for i in order], batch_size=SUB_BATCH))
        vectors = np.empty((len(texts), len(got[0])), dtype=np.float32)
        for i, v in zip(order, got, strict=True):
            vectors[i] = v
        return vectors

    failed = False
    for name, path in sets.items():
        texts = [
            json.loads(line)["text"]
            for line in path.read_text().splitlines()
            if line.strip()
        ]
        a, b = embed(upstream, texts), embed(out, texts)
        same = int(np.all(a == b, axis=1).sum())
        largest = float(np.abs(a.astype(np.float64) - b).max())
        a64, b64 = a.astype(np.float64), b.astype(np.float64)
        cos = (a64 * b64).sum(1) / np.sqrt((a64 * a64).sum(1) * (b64 * b64).sum(1))
        low = float(cos.min())
        print(
            f"{name}: {len(texts)} texts, {same} bitwise identical, largest difference {largest:.3g}, "
            f"minimum cosine {low:.8f}"
        )
        if low < MIN_COSINE:
            print(
                f"check: minimum cosine {low:.8f} in the {name} set, below {MIN_COSINE}",
                file=sys.stderr,
            )
            failed = True
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("convert", help="write the float32 folder")
    c.add_argument("upstream", type=Path)
    c.add_argument("out", type=Path)
    k = sub.add_parser("check", help="compare both folders' vectors")
    k.add_argument("upstream", type=Path)
    k.add_argument("out", type=Path)
    k.add_argument(
        "sets", nargs="+", metavar="NAME=TEXTS", help="a set's name and its JSON lines"
    )
    args = ap.parse_args(argv)
    if args.command == "convert":
        convert(args.upstream, args.out)
        return 0
    sets = {}
    for s in args.sets:
        name, sep, path = s.partition("=")
        if not sep or not name or not path:
            ap.error(f"not NAME=TEXTS: {s}")
        sets[name] = Path(path)
    return check(args.upstream, args.out, sets)


if __name__ == "__main__":
    sys.exit(main())
