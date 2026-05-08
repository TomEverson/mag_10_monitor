import json
import logging

from google.cloud import pubsub_v1

from config import GCP_PROJECT_ID

logger = logging.getLogger(__name__)


class Publisher:
    def __init__(self) -> None:
        self._client = pubsub_v1.PublisherClient()

    def publish(self, topic_name: str, payload: dict) -> None:
        """Fire-and-forget publish. Errors are logged via callback; never raises."""
        topic_path = self._client.topic_path(GCP_PROJECT_ID, topic_name)
        data = json.dumps(payload).encode("utf-8")
        try:
            future = self._client.publish(topic_path, data)
            future.add_done_callback(self._error_callback(topic_name))
        except Exception:
            logger.error("Failed to initiate publish to %s", topic_name, exc_info=True)

    @staticmethod
    def _error_callback(topic_name: str):
        def _cb(future):
            try:
                future.result()
            except Exception:
                logger.error("Publish to %s failed", topic_name, exc_info=True)
        return _cb
