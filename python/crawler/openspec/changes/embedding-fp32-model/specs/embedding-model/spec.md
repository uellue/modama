# Spec Delta

## Purpose

This capability covers the model file the warehouse's indexing embeds records with. The file is made once at image build from pinned upstream files and checked against their vectors. An operator can go back to the upstream file (@weber, item 283; requirements-pipeline 2.4).

## ADDED Requirements

### Requirement: The indexing embeds with a float32 file made from pinned upstream files
The Airflow image SHALL contain the model's graph with every float16 tensor stored as float32, the weights in a separate file, made at build from `qdrant/bge-small-en-v1.5-onnx-q` at revision `aa8f8b060edb00e03bfdd08813a2949946c8ba55`, each file checked by SHA-256 (design D1). Every file in the folder SHALL be readable by the image's user. By default, transform batches SHALL embed with it.

#### Scenario: A batch in the built image
- **WHEN** a transform batch starts in the built image with the image's own environment
- **THEN** it loads the float32 graph from the image's model folder, and its log line names that folder

#### Scenario: The worker's user reads the files
- **WHEN** the image is built
- **THEN** the build loads the float32 graph and its weight file in an ONNX Runtime session as uid 50000, the image's user, and stops if that fails

### Requirement: The build stops when an upstream file has moved
The image build SHALL stop when a fetched file's SHA-256 differs from its pin. It SHALL also stop, with a message naming both values, when the installed fastembed's description of `EMBEDDING_MODEL` names another source repository or model file than the pin.

#### Scenario: A changed upstream file
- **WHEN** a pinned file at the pinned revision has another SHA-256 than its pin, for example `tokenizer.json`
- **THEN** the build stops at fetching that file, and no image is tagged

#### Scenario: fastembed names another file
- **WHEN** a new upstream warehouse release brings a fastembed whose description of `BAAI/bge-small-en-v1.5` names another repository or model file
- **THEN** the build stops and names both

### Requirement: The float32 file's vectors stay close to the upstream file's
At build, fixed texts SHALL be embedded with both files in the image's transform venv, with the batches' settings. The build SHALL stop if any pair's cosine, in float64, is below 0.99999. For each set it SHALL report the bitwise-identical count, the largest absolute component difference and the minimum cosine.

#### Scenario: Short, mixed and long texts
- **WHEN** the check runs, which is whenever the stage's build cache is invalidated
- **THEN** the build log reports, for each of the short, mixed and long sets, the identical count, the largest difference and the minimum cosine, and the build goes on only if every cosine is at least 0.99999

#### Scenario: A file that changes the vectors
- **WHEN** the check is given a file whose vectors move more than the bound, for example the int8 file of `perf/grace-embedding/prepare_model.py` (minimum cosine 0.9647)
- **THEN** it exits with a non-zero status and names the set and the lowest cosine

### Requirement: The model folder names its model
The model folder SHALL hold a marker naming the model it was made from. A transform batch SHALL refuse to start, naming both, when the marker names another model than `EMBEDDING_MODEL`.

#### Scenario: Another model configured
- **WHEN** a transform batch starts with `EMBEDDING_MODEL` set to another model and `EMBEDDING_MODEL_PATH` set to the image's folder
- **THEN** the batch fails before embedding, and its error names the folder's model and `EMBEDDING_MODEL`

### Requirement: The operator can go back to the upstream file
An empty `EMBEDDING_MODEL_PATH` SHALL make transform batches load the file fastembed downloads, as before this change, without a rebuild.

#### Scenario: Going back
- **WHEN** `airflow-worker-transform` is started with `EMBEDDING_MODEL_PATH` set to an empty value
- **THEN** its batches load fastembed's own download, and the log line says so
