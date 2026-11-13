# Spec Delta

## Purpose

The service on grace that embeds the warehouse's record texts on the GPU, in place of the transform worker's CPU: what it accepts and answers, how close its vectors stay to the local path's, how it is protected, how it shares the GPU, and what the warehouse does when it cannot reach it (@weber, item 346; requirements-pipeline 2.4, 2.6, 2.9).

## ADDED Requirements

### Requirement: The service answers OpenAI's embeddings request
The service SHALL answer `POST /v1/embeddings` with a JSON body `{"model": …, "input": [texts]}` by `{"object": "list", "data": [{"object": "embedding", "index": i, "embedding": [384 numbers]}, …], "model": …}`: one vector per text, `index` the text's position in `input`, each vector of unit length.

#### Scenario: Three texts
- **WHEN** the service gets a request with the model `bge-small-en-v1.5` and three texts
- **THEN** it answers 200 with three vectors of 384 numbers, indexes 0, 1 and 2 in the order of the texts, each of length 1 within 1e-6

#### Scenario: The texts in another order
- **WHEN** the same three texts are sent in reverse order
- **THEN** the vector at index 0 is the one that was at index 2 before

### Requirement: The service's vectors agree with the local path's
For any text, the vector from the service and the vector the transform worker computes locally for the same text SHALL have a cosine, computed in float64, of at least 0.99999 (the bound of change `embedding-fp32-model`; design D4).

#### Scenario: Short, mixed and long texts
- **WHEN** the check instrument sends the fixed short, mixed and long sets (512 texts each) to the service and embeds them locally in the transform worker's image
- **THEN** it reports the minimum cosine per set, and each is at least 0.99999

#### Scenario: Records of staging
- **WHEN** a sample of 1,000 of staging's records is indexed once with the service and once locally
- **THEN** every pair of stored vectors has a cosine of at least 0.99999

### Requirement: Texts longer than the model's window are cut at tokens
The service SHALL embed a text longer than the model's 512 tokens from its first 512 tokens, special tokens included, as the local path does, and SHALL NOT refuse it.

#### Scenario: A text of 2,000 tokens
- **WHEN** the service gets a text of about 2,000 tokens
- **THEN** it answers 200, and the vector agrees within the bound with the local path's vector of the same whole text

#### Scenario: Only the first 512 tokens count
- **WHEN** two texts of over 512 tokens share their first 600 tokens and differ after them
- **THEN** the service gives both the same vector, up to a cosine of 1 − 1e-7

### Requirement: The warehouse sends its texts uncut
With the service configured, the transform worker SHALL send each record's embedding text whole, without cutting it at a number of characters.

#### Scenario: A long description
- **WHEN** a batch holds a record whose embedding text has 5,000 characters
- **THEN** the request to the service holds all 5,000 characters of it, and the stored vector agrees within the bound with the local path's for that record

### Requirement: Requests need the service's token
The service SHALL refuse with 401, and embed nothing, a request whose `Authorization` header is not `Bearer` followed by the token read from its token file. The token SHALL NOT appear in the repository, in the service's log, or in the warehouse's log.

#### Scenario: No token
- **WHEN** a request has no `Authorization` header
- **THEN** the service answers 401

#### Scenario: A wrong token
- **WHEN** a request carries another token
- **THEN** the service answers 401, and its log line names neither token

### Requirement: The service serves one model
The service SHALL refuse with 400 a request that names another model than `bge-small-en-v1.5`, the name the warehouse sends for `BAAI/bge-small-en-v1.5`, and the answer SHALL name the model it serves.

#### Scenario: Another model asked for
- **WHEN** a request names the model `nomic-embed-text-v1.5`
- **THEN** the service answers 400, naming `bge-small-en-v1.5`

### Requirement: The service names its model file
`GET /health` SHALL answer, without a token, the model's repository, revision and file and the execution provider in use. The service SHALL load the same pinned files as the local path.

#### Scenario: The health answer
- **WHEN** the service runs on grace's GPU
- **THEN** `GET /health` names `qdrant/bge-small-en-v1.5-onnx-q`, the revision `aa8f8b060edb00e03bfdd08813a2949946c8ba55`, the model file and `CUDAExecutionProvider`

### Requirement: The service listens on grace's loopback only
The service SHALL accept connections on 127.0.0.1 only; other hosts reach it through the SSH tunnel.

#### Scenario: From another host
- **WHEN** a host other than grace connects to grace's network address at the service's port
- **THEN** the connection is refused, and `ss -ltn` on grace lists the port on 127.0.0.1 only

### Requirement: The service keeps its GPU memory within a limit
The service's ONNX Runtime memory on the GPU SHALL stay within its configured limit. A batch that would need more SHALL get a 503 answer, and the service SHALL go on serving.

#### Scenario: A limit too small for a batch
- **WHEN** the service runs with a limit too small for 256 texts of 512 tokens and gets such a batch
- **THEN** it answers 503, and answers the next small batch with 200

### Requirement: The service does not keep or log the texts
The service SHALL NOT store the texts it gets, and its log line for a request SHALL hold the number of texts, the number of tokens, the time taken and the status, never text.

#### Scenario: A marker in a text
- **WHEN** a request holds a text with a unique marker string
- **THEN** the service's journal does not contain the marker

### Requirement: The service restarts after a failure
When the service's process ends without being stopped, it SHALL be started again after 30 seconds.

#### Scenario: The process is killed
- **WHEN** the service's main process is killed with SIGKILL
- **THEN** systemd starts it again, and `GET /health` answers again within a minute

### Requirement: The warehouse embeds locally when the service fails
When a request to the service fails after the warehouse's retries (no connection, an error status, no answer within the timeout), the transform worker SHALL embed that batch locally and index it. Each such batch SHALL be counted as a fallback by `field-test/batch-times.sh`.

#### Scenario: The tunnel is down
- **WHEN** a transform batch runs while nothing listens at `EMBED_API_URL`
- **THEN** the batch is embedded locally within 10 seconds of its first attempt, indexed, and `batch-times.sh` shows it as a fallback

#### Scenario: The service does not answer
- **WHEN** the service accepts the connection but sends no answer
- **THEN** the batch is embedded locally within 3 minutes of its first attempt, indexed, and shown as a fallback

#### Scenario: A wrong token
- **WHEN** `EMBED_API_KEY` holds another token than the service's
- **THEN** every batch is embedded locally and shown as a fallback, and the warehouse's log shows the 401 without the token

### Requirement: The way back is an empty URL
With an empty `EMBED_API_URL`, the transform worker SHALL embed locally and send no request, as before this change.

#### Scenario: Switched off
- **WHEN** `EMBED_API_URL` is empty in the deployment's env file and `airflow-worker-transform` is recreated
- **THEN** the next batches embed locally, the service gets no request, and `batch-times.sh` shows them as local, not as fallbacks
