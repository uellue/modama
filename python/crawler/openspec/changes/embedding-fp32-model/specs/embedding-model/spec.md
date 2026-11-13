# Spec Delta

## Purpose

This capability covers the model file the warehouse's indexing embeds records with: the file is made once at image build from the pinned upstream file, it is checked against that file's vectors, and an operator can go back to the upstream file (@weber, item 283; requirements-pipeline 2.4).

## ADDED Requirements

### Requirement: The indexing embeds with a float32 file made from the pinned upstream file
The warehouse's Airflow image SHALL contain the embedding model's graph with every float16 weight stored as float32, made at image build from the upstream file pinned by repository, revision and SHA-256. The weights SHALL be in a separate file next to the graph. By default the transform batches SHALL embed with this file.

#### Scenario: A batch in the built image
- **WHEN** a transform batch starts in the built image with the image's own environment
- **THEN** it loads the float32 graph from the image's model folder, and its log line names that folder

### Requirement: The build stops when the upstream file has moved
The image build SHALL stop with a message naming the expected and the found value when the downloaded upstream file's SHA-256 differs from the pin, or when the installed fastembed's description of `EMBEDDING_MODEL` names another source repository or model file than the pin.

#### Scenario: A changed upstream file
- **WHEN** the pinned revision's `model_optimized.onnx` has another SHA-256 than the pin
- **THEN** the build stops with both hashes in its message, and no image is tagged

#### Scenario: fastembed names another file
- **WHEN** a new upstream warehouse release brings a fastembed whose description of `BAAI/bge-small-en-v1.5` names another repository or model file
- **THEN** the build stops and names both

### Requirement: The float32 file's vectors agree with the upstream file's
At image build, the same fixed texts SHALL be embedded with the upstream file and with the float32 file, in the image's transform venv with the batches' own embedding settings. The build SHALL stop when, for any text, a vector component differs by more than the bound chosen in design D4.

#### Scenario: Short, mixed and long texts
- **WHEN** the image is built
- **THEN** the build log reports, for each of the short, mixed and long sets, how many vectors are bitwise identical and the largest absolute difference of a component, and the build goes on only if every difference is within the bound

#### Scenario: A file that changes the vectors
- **WHEN** the check is given a float32 file whose vectors are off by more than the bound (for example the int8 file of `perf/grace-embedding/prepare_model.py`)
- **THEN** it exits with a non-zero status and names the set and the largest difference

### Requirement: The operator can go back to the upstream file
An empty `EMBEDDING_MODEL_PATH` SHALL make the transform batches load the file fastembed downloads, as before this change, without a rebuild.

#### Scenario: Going back
- **WHEN** `airflow-worker-transform` is started with `EMBEDDING_MODEL_PATH` set to an empty value
- **THEN** its batches load fastembed's own download, and the log line says so
