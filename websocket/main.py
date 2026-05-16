import asyncio
import json
import logging
import signal
import time

import websockets

from config import FINNHUB_WS_URL, PUBSUB_TOPIC_RAW_TRADES, SYMBOLS
from publisher import Publisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

_BACKOFF = [5, 10, 20, 40, 80, 120]
_RESET_AFTER_SECS = 60


def _backoff_delay(attempt: int) -> int:
    return _BACKOFF[min(attempt, len(_BACKOFF) - 1)]


def _validate(trade: dict) -> bool:
    if trade.get("s") not in SYMBOLS:
        return False
    p = trade.get("p")
    if not p or p <= 0:
        return False
    v = trade.get("v")
    if v is None or v < 0:
        return False
    t = trade.get("t")
    if t is None:
        return False
    if time.time() * 1000 - t > 60_000:
        logger.debug("Stale trade discarded: %s t=%d", trade.get("s"), t)
        return False
    return True


async def _run(shutdown: asyncio.Event) -> None:
    publisher = Publisher()
    attempt = 0

    while not shutdown.is_set():
        connect_time: float | None = None
        try:
            logger.info("Connecting to Finnhub (attempt %d)", attempt + 1)
            async with websockets.connect(FINNHUB_WS_URL) as ws:
                connect_time = time.monotonic()

                for sym in SYMBOLS:
                    await ws.send(json.dumps({"type": "subscribe", "symbol": sym}))
                logger.info("Subscribed to %d symbols", len(SYMBOLS))

                async for raw in ws:
                    if shutdown.is_set():
                        break
                    try:
                        frame = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    ftype = frame.get("type")
                    if ftype == "ping":
                        await ws.send(json.dumps({"type": "pong"}))
                        continue
                    if ftype != "trade":
                        logger.debug("Discarding frame type=%s", ftype)
                        continue

                    for trade in frame.get("data") or []:
                        if not _validate(trade):
                            continue
                        # Publish raw trade — only fields the Detection VM needs
                        publisher.publish(PUBSUB_TOPIC_RAW_TRADES, {
                            "s": trade["s"],
                            "p": trade["p"],
                            "v": trade["v"],
                            "t": trade["t"],
                        })

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            elapsed = time.monotonic() - connect_time if connect_time else 0
            if elapsed >= _RESET_AFTER_SECS:
                attempt = 0
            delay = _backoff_delay(attempt)
            logger.warning(
                "Connection lost (%s). Reconnecting in %ds (attempt %d)",
                exc, delay, attempt + 1,
            )
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
            attempt += 1


async def _main() -> None:
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler():
        logger.info("Shutdown signal received — stopping")
        shutdown.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    await _run(shutdown)
    logger.info("WebSocket VM stopped")


if __name__ == "__main__":
    asyncio.run(_main())
