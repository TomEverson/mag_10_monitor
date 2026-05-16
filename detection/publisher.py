import json
import logging

from google.cloud import pubsub_v1

from config import GCP_PROJECT_ID

logger = logging.getLogger(__name__)


class Publisher:
    def __init__(self) -> None:
        self._client = pubsub_v1.PublisherClient()

    def publish(self, topic_name: str, payload: dict) -> None:
        topic_path = self._client.topic_path(GCP_PROJECT_ID, topic_name)
        data = json.dumps(payload).encode("utf-8")
        signal_type = payload.get("signal_type", "")
        try:
            future = self._client.publish(
                topic_path,
                data,
                signal_type=signal_type,  # Pub/Sub message attribute for filtering
            )
            future.add_done_callback(self._error_callback(topic_name, signal_type))
        except Exception:
            logger.error(
                "Failed to initiate publish to %s [%s]", topic_name, signal_type,
                exc_info=True,
            )

    @staticmethod
    def _error_callback(topic_name: str, signal_type: str):
        def _cb(future):
            try:
                future.result()
            except Exception:
                logger.error(
                    "Publish to %s [%s] failed", topic_name, signal_type,
                    exc_info=True,
                )
        return _cb
