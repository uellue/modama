# The Airflow image of the warehouse with our patches on top (patches/warehouse/, applied in
# order; a patch that does not apply fails the build), the CPU budget's start script
# (cpu-budget/budget.py, README "CPU budget") and the embedding model stored in float32 (stage
# `model`, README "The embedding model"). Build context: patches/warehouse; named contexts `budget`:
# cpu-budget/, `embedding-model`: embedding-model/, `texts`: perf/grace-embedding/ (gen_texts.py).
# The base is upstream's Dockerfile built unchanged, as the image of the build-only service
# airflow-upstream (docker-compose.yml), which ./uptest.sh and ./upstaging.sh build first. Drop a
# patch once upstream has it.
FROM search-stack-airflow-upstream:3.3.2 AS upstream

# upstream's image has no patch
FROM busybox:1.37.0 AS patched
WORKDIR /w
COPY --from=upstream /opt/airflow/dags airflow/dags
COPY --from=upstream /opt/airflow/project/src src
COPY *.patch /patches/
RUN for p in /patches/*.patch; do echo "applying $p" && patch -p1 -i "$p" || exit 1; done

# The model fastembed downloads for BAAI/bge-small-en-v1.5, its graph stored in float32, made from the
# pinned upstream files (change embedding-fp32-model; the pins also in embedding-model/fp32.py, which
# test_fp32.py compares with these lines). A changed upstream file stops the build here.
FROM upstream AS model
WORKDIR /tmp/model
ADD --chown=airflow:root --checksum=sha256:51f1bd0addd6e859e42c2c8021a5e5461385bb676a649f4b269aa445449f2431 \
    https://huggingface.co/qdrant/bge-small-en-v1.5-onnx-q/resolve/aa8f8b060edb00e03bfdd08813a2949946c8ba55/model_optimized.onnx upstream/
ADD --chown=airflow:root --checksum=sha256:d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66 \
    https://huggingface.co/qdrant/bge-small-en-v1.5-onnx-q/resolve/aa8f8b060edb00e03bfdd08813a2949946c8ba55/tokenizer.json upstream/
ADD --chown=airflow:root --checksum=sha256:0b29c7bfc889e53b36d9dd3e686dd4300f6525110eaa98c76a5dafceb2029f53 \
    https://huggingface.co/qdrant/bge-small-en-v1.5-onnx-q/resolve/aa8f8b060edb00e03bfdd08813a2949946c8ba55/tokenizer_config.json upstream/
ADD --chown=airflow:root --checksum=sha256:5d5b662e421ea9fac075174bb0688ee0d9431699900b90662acd44b2a350503a \
    https://huggingface.co/qdrant/bge-small-en-v1.5-onnx-q/resolve/aa8f8b060edb00e03bfdd08813a2949946c8ba55/special_tokens_map.json upstream/
ADD --chown=airflow:root --checksum=sha256:13582bcf2effc85b7bf3d3f5532e686bc1c9ce86bb009d10f0ec33cbe92299dd \
    https://huggingface.co/qdrant/bge-small-en-v1.5-onnx-q/resolve/aa8f8b060edb00e03bfdd08813a2949946c8ba55/config.json upstream/
COPY --from=embedding-model fp32.py requirements-onnx.txt ./
COPY --from=texts gen_texts.py ./
# onnx only in this stage's venv; the check runs in the transform venv, as the batches embed
RUN uv venv -q onnx-venv --python /usr/python/bin/python3 \
 && uv pip install -q --python onnx-venv/bin/python --require-hashes -r requirements-onnx.txt \
 && onnx-venv/bin/python fp32.py convert upstream bge-small-en-v1.5-fp32 \
 && python3 -I gen_texts.py short.jsonl --n 64 --long-share 0 --seed 1 \
 && python3 -I gen_texts.py mixed.jsonl --n 64 --long-share 0.12 --seed 2 \
 && python3 -I gen_texts.py long.jsonl --n 32 --long-share 1 --seed 3 \
 && FASTEMBED_CACHE_DIR=/tmp/model/cache /opt/airflow/transform-venv/bin/python fp32.py check \
      upstream bge-small-en-v1.5-fp32 short=short.jsonl mixed=mixed.jsonl long=long.jsonl

FROM upstream
COPY --from=patched --chown=airflow:root /w/airflow/dags /opt/airflow/dags
COPY --from=patched --chown=airflow:root /w/src /opt/airflow/project/src
COPY --from=budget budget.py /opt/modama/budget.py
# owned by root, 0644 (fp32.py convert): the batches read it and cannot change it
COPY --from=model --chown=root:root /tmp/model/bge-small-en-v1.5-fp32 /opt/modama/models/bge-small-en-v1.5-fp32
# patch 0004: the batches load this folder; empty: fastembed's own download (README, "The embedding model")
ENV EMBEDDING_MODEL_PATH=/opt/modama/models/bge-small-en-v1.5-fp32
# the image's user (airflow, uid 50000) can open the graph and its weight file
RUN /opt/airflow/transform-venv/bin/python -c "import onnxruntime as o, sys; \
o.InferenceSession(sys.argv[1] + '/model_optimized.onnx', providers=['CPUExecutionProvider']); \
print('model loads as uid', __import__('os').getuid())" "$EMBEDDING_MODEL_PATH"
