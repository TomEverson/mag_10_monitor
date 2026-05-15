# Spec: Listener Services

## Overview

The listener role is split across **two separate VMs**:

| VM | Name | Responsibility |
|---|---|---|
| WebSocket VM | `mag10-websocket-vm-prod` | Ingest raw trades from Finnhub, publish to Pub/Sub |
| Detection VM | `mag10-detection-vm-prod` | Consume raw trades, run detectors, publish signals |

Both run on e2-micro instances. Neither writes to BigQuery or GCS directly.

---

## WebSocket VM

### Overview

The WebSocket VM is the only service with a Finnhub connection. Its sole
responsibility is to receive raw trades and publish them to the
`mag10-raw-trades` Pub/Sub topic. It performs no detection logic.

### Entry Point

`listener/main.py`

1. Load configuration from environment variables via `config.py`.
2. Initialise the Pub/Sub publisher (`publisher.py`).
3. Open the WebSocket connection and enter the receive loop.
4. Handle SIGTERM and SIGINT gracefully — drain in-flight publishes, close
   WebSocket cleanly before exiting.

### Concurrency Model

asyncio throughout. All I/O (WebSocket receive, Pub/Sub publish) is async.

| Component | Async? | Notes |
|---|---|---|
| WebSocket receive loop | Yes | `async for message in ws` |
| Trade validation | No | Synchronous, sub-millisecond |
| Pub/Sub publish | Yes | Fire-and-forget with error callback |

### WebSocket Lifecycle

```
start
  │
  ▼
connect_with_backoff()
  │  opens wss://ws.finnhub.io?token=...
  │  subscribes all 10 symbols
  ▼
receive_loop()
  │  for each frame:
  │    if type == "trade": validate + publish each trade to mag10-raw-trades
  │    if type == "ping":  send pong
  │    else: log DEBUG, discard
  ▼
on_disconnect()
  │  log warning with close code and reason
  │  wait backoff delay
  └► connect_with_backoff()  (retry loop)
```

The WebSocket VM never exits the reconnect loop on its own — it retries
indefinitely until SIGTERM is received.

### Backoff Schedule

| Attempt | Delay |
|---|---|
| 1 | 5s |
| 2 | 10s |
| 3 | 20s |
| 4 | 40s |
| 5 | 80s |
| 6+ | 120s |

Delay resets to 5s after a connection open for at least 60 seconds.

### Trade Validation

Before publishing, each trade must pass validation:

1. `s` (symbol) must be in `SYMBOLS`.
2. `p` (price) must be present and > 0.
3. `v` (volume) must be present and ≥ 0.
4. `t` (timestamp ms) must be present.
5. Trade must not be stale: `now_ms - t <= 60_000` (60-second staleness cutoff).

Invalid trades are discarded silently (DEBUG log only).

### Publisher

`listener/publisher.py` wraps `PublisherClient`. It must:

- Serialise the raw trade dict to JSON (UTF-8 bytes).
- Call `client.publish(topic_path, data)`.
- Catch and log all exceptions at ERROR level — never raise to the caller.

Topic path: `projects/{GCP_PROJECT_ID}/topics/mag10-raw-trades`

### Configuration (`config.py`)

| Variable | Source | Description |
|---|---|---|
| `FINNHUB_API_KEY` | Secret Manager | Finnhub WebSocket auth |
| `GCP_PROJECT_ID` | Env | GCP project |
| `PUBSUB_TOPIC_RAW_TRADES` | Env | Raw trades topic name |
| `SYMBOLS` | `config.py` | Hardcoded set of 10 symbols |

### Logging

| Level | When |
|---|---|
| INFO | Startup, connected, reconnecting |
| WARNING | Disconnect, stale trade discarded |
| DEBUG | Every trade received, pings, discarded frames |
| ERROR | Publish failures, unhandled exceptions |

---

## Detection VM

### Overview

The Detection VM subscribes to `mag10-raw-trades` (pull subscription),
runs all four stateful detectors against each trade, and publishes signals
to `mag10-processed-signals`. It has no Finnhub connection.

### Entry Point

`detection/main.py`

1. Load configuration from environment variables.
2. Run warm-start procedure (see `spec/pipeline/bronze.md`).
3. Initialise the Pub/Sub subscriber (pull) and publisher.
4. Enter the message receive loop.
5. Handle SIGTERM and SIGINT gracefully.

### Concurrency Model

asyncio throughout.

| Component | Async? | Notes |
|---|---|---|
| Pub/Sub pull loop | Yes | Streaming pull via `SubscriberClient` |
| Detector `.process(trade)` calls | No | Synchronous CPU work in event loop |
| Pub/Sub publish | Yes | Fire-and-forget with error callback |
| Sector snapshot timer | Yes | `asyncio.create_task` with `asyncio.sleep` loop |

### Message Processing

For each raw trade message received from `mag10-raw-trades`:

1. Parse the JSON payload — fields `s`, `p`, `v`, `t`.
2. Call `detector.process(trade)` for each detector in order:
   volume → momentum → volatility → sector.
3. For each non-None result, publish to `mag10-processed-signals` with
   a Pub/Sub message attribute `signal_type` set to the signal's
   `signal_type` field value.
4. Ack the message after all detectors have processed it.

### Pub/Sub Message Attributes

The Detection VM sets the `signal_type` attribute on each published message
to enable Pub/Sub filtering on the `mag10-processed-signals` topic:

```python
publisher.publish(
    topic_path,
    data=json.dumps(signal).encode(),
    signal_type=signal["signal_type"]   # Pub/Sub message attribute
)
```

### Detector Interface

Each detector in `detection/detectors/` implements `BaseDetector`:

```python
class BaseDetector(ABC):
    @abstractmethod
    def process(self, trade: dict) -> dict | None:
        """Return a signal dict if fired, None otherwise."""

    @abstractmethod
    def reset(self) -> None:
        """Reset all rolling windows (called on reconnect)."""
```

The sector detector's `process()` always returns `None` — it publishes
via a separate timer loop.

### Sector Snapshot Timer

```python
async def sector_snapshot_loop(sector_detector, publisher):
    while True:
        await asyncio.sleep(SECTOR_SNAPSHOT_INTERVAL_SECS)
        payload = sector_detector.get_snapshot()
        publisher.publish(topic_path, payload, signal_type="sector_snapshot")
```

### Configuration

| Variable | Source | Description |
|---|---|---|
| `GCP_PROJECT_ID` | Env | GCP project |
| `PUBSUB_SUBSCRIPTION_RAW` | Env | Raw trades pull subscription name |
| `PUBSUB_TOPIC_PROCESSED` | Env | Processed signals topic name |
| `GCS_BUCKET_RAW` | Env | Bronze/Silver GCS bucket |
| Detector constants | `config.py` | All thresholds and window sizes |
| `SYMBOLS` | `config.py` | Hardcoded set of 10 symbols |

### Logging

| Level | When |
|---|---|
| INFO | Startup, warm-start complete, signal detected |
| WARNING | Message parse error, publish failure |
| DEBUG | Every trade processed |
| ERROR | Unhandled exception, repeated failures |

### Resource Constraints

Both VMs run on e2-micro (1 vCPU, 1 GB RAM):

- Rolling windows use `collections.deque` — memory bounded.
- No disk writes from either VM process.
- Detection VM: no outbound connection to Finnhub.
- WebSocket VM: no detector state, minimal memory footprint.
