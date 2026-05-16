import asyncio
import json
import logging
import signal

from google.cloud import pubsub_v1

from config import (
    GCP_PROJECT_ID,
    PUBSUB_SUBSCRIPTION_RAW,
    PUBSUB_TOPIC_PROCESSED,
    SECTOR_SNAPSHOT_INTERVAL_SECS,
)
from detectors.momentum import MomentumDetector
from detectors.sector import SectorDetector
from detectors.volatility import VolatilityDetector
from detectors.volume import VolumeDetector
from publisher import Publisher
from warm_start import warm_start

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


async def _snapshot_loop(
    sector: SectorDetector,
    publisher: Publisher,
    shutdown: asyncio.Event,
) -> None:
    while not shutdown.is_set():
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=SECTOR_SNAPSHOT_INTERVAL_SECS)
        except asyncio.TimeoutError:
            pass
        if shutdown.is_set():
            break
        publisher.publish(PUBSUB_TOPIC_PROCESSED, sector.get_snapshot())
        logger.info("Sector snapshot published")


def _process_message(
    message: pubsub_v1.types.PubsubMessage,
    detectors: list[tuple],
    publisher: Publisher,
) -> None:
    try:
        trade = json.loads(message.data.decode("utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse message: %s", exc)
        message.ack()
        return

    for detector, _ in detectors:
        result = detector.process(trade)
        if result is not None:
            publisher.publish(PUBSUB_TOPIC_PROCESSED, result)
            logger.info("Signal %s %s", result["signal_type"], result["symbol"])

    message.ack()


async def _run(shutdown: asyncio.Event) -> None:
    publisher = Publisher()

    volume = VolumeDetector()
    momentum = MomentumDetector()
    volatility = VolatilityDetector()
    sector = SectorDetector()

    detectors: list[tuple] = [
        (volume,     PUBSUB_TOPIC_PROCESSED),
        (momentum,   PUBSUB_TOPIC_PROCESSED),
        (volatility, PUBSUB_TOPIC_PROCESSED),
        (sector,     None),
    ]

    logger.info("Starting warm-start from GCS Bronze...")
    warm_start([d for d, _ in detectors])

    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(GCP_PROJECT_ID, PUBSUB_SUBSCRIPTION_RAW)

    snapshot_task = asyncio.create_task(
        _snapshot_loop(sector, publisher, shutdown)
    )

    loop = asyncio.get_running_loop()

    def _on_message(message: pubsub_v1.types.PubsubMessage) -> None:
        loop.call_soon_threadsafe(_process_message, message, detectors, publisher)

    logger.info("Starting pull subscription on %s", subscription_path)
    streaming_pull = subscriber.subscribe(subscription_path, callback=_on_message)

    try:
        await shutdown.wait()
    finally:
        logger.info("Shutting down subscriber...")
        streaming_pull.cancel()
        streaming_pull.result(timeout=5)
        snapshot_task.cancel()
        try:
            await snapshot_task
        except asyncio.CancelledError:
            pass
        subscriber.close()


async def _main() -> None:
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler():
        logger.info("Shutdown signal received — stopping")
        shutdown.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    await _run(shutdown)
    logger.info("Detection VM stopped")


if __name__ == "__main__":
    asyncio.run(_main())
