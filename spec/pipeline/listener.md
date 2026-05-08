# Spec: Listener

## Overview

The listener is a Python process that runs continuously on an e2-micro GCP VM.
It owns the Finnhub WebSocket connection, dispatches incoming trades to all
four detectors, and publishes signals to Pub/Sub. It has no HTTP interface and
no external dependencies beyond Finnhub and Pub/Sub.

---

## Entry Point

`listener/main.py` is the entry point. It must:

1. Load configuration from environment variables (via `config.py`).
2. Initialise the Pub/Sub publisher (`publisher.py`).
3. Initialise all four detector instances.
4. Start the sector snapshot timer (async task or thread).
5. Open the WebSocket connection and enter the receive loop.
6. Handle SIGTERM and SIGINT gracefully (drain in-flight publishes, close
   the WebSocket cleanly before exiting).

---

## Concurrency Model

The listener uses **asyncio** throughout. All I/O (WebSocket, Pub/Sub publish)
is async. Detector logic is synchronous CPU work executed directly in the event
loop — it must remain fast (sub-millisecond per trade) to avoid blocking the
loop.

| Component              | Async? | Notes |
|------------------------|--------|-------|
| WebSocket receive loop | Yes    | `async for message in ws` |
| Detector `.process(trade)` calls | No | Called synchronously inside receive loop |
| Pub/Sub publish        | Yes    | Non-blocking; fire-and-forget with error logging |
| Sector snapshot timer  | Yes    | `asyncio.create_task` with `asyncio.sleep` loop |

---

## WebSocket Lifecycle

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
  │    if type == "trade": dispatch to detectors
  │    if type == "ping":  send pong
  │    else: log DEBUG, discard
  ▼
on_disconnect()
  │  log warning with close code and reason
  │  wait backoff delay
  └► connect_with_backoff()  (retry loop)
```

The listener never exits the reconnect loop on its own — it retries
indefinitely until SIGTERM is received.

### Backoff schedule

| Attempt | Delay |
|---------|-------|
| 1       | 5s    |
| 2       | 10s   |
| 3       | 20s   |
| 4       | 40s   |
| 5       | 80s   |
| 6+      | 120s  |

Delay resets to 5s after a connection that remains open for at least 60 seconds
(considered a successful recovery).

---

## Trade Dispatch

For each trade in a received frame:

1. Validate the trade (see `spec/data-sources.md` — Data Quality).
2. For each detector: call `detector.process(trade)`.
3. If `detector.process(trade)` returns a signal dict, call
   `publisher.publish(topic, signal)`.
4. Continue to the next trade.

Detectors are called in this fixed order: volume → momentum → volatility →
sector. All four are called for every valid trade regardless of whether earlier
detectors fired.

---

## Detector Interface

Each detector in `listener/detectors/` must implement the `BaseDetector`
abstract class defined in `listener/detectors/base.py`:

```python
class BaseDetector(ABC):
    @abstractmethod
    def process(self, trade: dict) -> dict | None:
        """
        Receive one validated trade. Return a signal dict if a signal fired,
        or None otherwise.
        """

    @abstractmethod
    def reset(self) -> None:
        """Reset all rolling windows and internal state (called on reconnect)."""
```

The sector detector's `process` method always returns `None` — it publishes
signals via a separate timer path, not via the return value.

---

## Sector Snapshot Timer

A separate asyncio task runs a loop:

```python
async def sector_snapshot_loop(sector_detector, publisher):
    while True:
        await asyncio.sleep(SECTOR_SNAPSHOT_INTERVAL_SECS)
        payload = sector_detector.get_snapshot()
        await publisher.publish(PUBSUB_TOPIC_SECTOR, payload)
```

`sector_detector.get_snapshot()` is synchronous and returns the signal dict
defined in `spec/detectors/sector.md`. The task is cancelled on SIGTERM.

---

## Publisher

`listener/publisher.py` wraps the Google Cloud Pub/Sub `PublisherClient`. It
must:

- Serialise the signal dict to JSON (UTF-8 bytes).
- Call `client.publish(topic_path, data)` — this is asynchronous in the GCP
  client library; the returned future must be awaited or scheduled, and any
  exception must be caught and logged at ERROR level.
- Not raise exceptions to the caller — publish failures are logged but do not
  crash the receive loop.

Topic paths are fully qualified:
`projects/{GCP_PROJECT_ID}/topics/{PUBSUB_TOPIC_*}`

---

## Configuration (`config.py`)

`listener/config.py` reads all configuration from environment variables and
defines detector constants. It must not contain any default credentials.

| Variable                    | Source           | Description |
|-----------------------------|------------------|-------------|
| `FINNHUB_API_KEY`           | Env / Secret Mgr | Finnhub WebSocket auth |
| `GCP_PROJECT_ID`            | Env              | GCP project |
| `PUBSUB_TOPIC_VOLUME`       | Env              | Topic name (not full path) |
| `PUBSUB_TOPIC_MOMENTUM`     | Env              | Topic name |
| `PUBSUB_TOPIC_VOLATILITY`   | Env              | Topic name |
| `PUBSUB_TOPIC_SECTOR`       | Env              | Topic name |
| Detector constants          | `config.py`      | All thresholds and window sizes |
| `SYMBOLS`                   | `config.py`      | Hardcoded list of 10 symbols |

---

## Logging

| Level   | When |
|---------|------|
| INFO    | Startup, successful connection, reconnect, signal detected |
| WARNING | Disconnect, stale trade discarded, publish failure |
| DEBUG   | Every trade received, pings, discarded frames |
| ERROR   | Unhandled exception in receive loop, repeated publish failures |

Logs are written to stdout in plain text. GCP Cloud Logging ingests stdout
from the VM automatically.

---

## Resource Constraints

Running on e2-micro (1 vCPU, 1 GB RAM):

- Each rolling window is a `collections.deque(maxlen=N)` — memory bounded.
- Maximum total rolling window memory across all detectors and symbols:
  `4 detectors × 10 symbols × max_window_size × 8 bytes (float)` ≈ negligible.
- No background threads other than the Pub/Sub client's internal thread pool.
- No disk writes from the listener process.
