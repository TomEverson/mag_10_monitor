import logging

from google.cloud import bigquery

logger = logging.getLogger(__name__)

_client = bigquery.Client()


def insert_rows(table_ref: str, rows: list[dict], row_ids: list[str]) -> None:
    """
    Stream-insert rows into BigQuery. Raises RuntimeError if any row fails.
    row_ids are used as BigQuery insertIds for ~1-minute deduplication.
    """
    errors = _client.insert_rows_json(table_ref, rows, row_ids=row_ids)
    if errors:
        raise RuntimeError(f"BigQuery streaming insert errors: {errors}")
