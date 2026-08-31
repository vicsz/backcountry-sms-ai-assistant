"""Best-effort, sender-scoped DynamoDB message context."""

import logging
import os
import re
import time
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .models import CONTEXT_HISTORY_LIMIT, CONTEXT_TTL_SECONDS, ContextInteraction
from .telemetry import emit_event
from .tracing import trace_span

LOGGER = logging.getLogger(__name__)


def normalized_e164(value: object) -> str:
    """Normalize only a phone value already authorized for this Lambda."""
    if not isinstance(value, str):
        return ""
    digits = re.sub(r"[^0-9]", "", value)
    return f"+{digits}" if 8 <= len(digits) <= 15 else ""


def context_table_name() -> str:
    return os.environ.get("MESSAGE_CONTEXT_TABLE", "")


def load_context(user_phone: str) -> tuple[list[ContextInteraction], bool]:
    """Read only this sender's newest unexpired completed exchanges; failure is non-blocking."""
    table = context_table_name()
    if not table:
        return ([], True)
    now = int(time.time())
    try:
        with trace_span("context.read", provider="dynamodb"):
            client = _dynamodb_client()
            history: list[ContextInteraction] = []
            exclusive_start_key: Mapping[str, Any] | None = None
            while len(history) < CONTEXT_HISTORY_LIMIT:
                query_kwargs: dict[str, Any] = {
                    "TableName": table,
                    "KeyConditionExpression": "user_phone_e164 = :phone",
                    "ExpressionAttributeValues": {":phone": {"S": user_phone}, ":now": {"N": str(now)}},
                    "ExpressionAttributeNames": {"#ttl": "ttl"},
                    "FilterExpression": "#ttl > :now AND attribute_exists(output_body)",
                    "ScanIndexForward": False,
                    "Limit": CONTEXT_HISTORY_LIMIT,
                }
                if exclusive_start_key is not None:
                    query_kwargs["ExclusiveStartKey"] = exclusive_start_key
                response = client.query(**query_kwargs)
                items = response.get("Items", [])
                if not isinstance(items, list):
                    raise TypeError("invalid_context_query")
                history.extend(
                    row
                    for item in items
                    if isinstance(item, Mapping)
                    for row in [_context_from_item(item)]
                    if row is not None
                )
                if len(history) >= CONTEXT_HISTORY_LIMIT:
                    break
                next_key = response.get("LastEvaluatedKey")
                if not isinstance(next_key, Mapping) or not next_key:
                    break
                exclusive_start_key = next_key
            return (sorted(history[-CONTEXT_HISTORY_LIMIT:], key=lambda row: row.created_at), True)
    except Exception as error:  # noqa: BLE001 - context must never suppress an SMS reply
        LOGGER.info("message_context_read_failed error_type=%s", type(error).__name__)
        emit_event("context_read", "failure", outcome="storage_unavailable", metrics={"ContextReadFailures": 1})
        return ([], False)


def _context_from_item(item: Mapping[str, Any]) -> ContextInteraction | None:
    try:
        input_body, output_body, created_at = item["input_body"]["S"], item["output_body"]["S"], item["created_at"]["S"]
    except (KeyError, TypeError):
        return None
    return ContextInteraction(input_body, output_body, created_at) if all(isinstance(v, str) for v in (input_body, output_body, created_at)) else None


def reserve_interaction(user_phone: str, message_id: str, created_at: str, input_body: object) -> bool | None:
    """Conditionally create an empty-output row before invoking Bedrock to stop SNS duplicates."""
    table = context_table_name()
    if not table:
        return True
    body = input_body if isinstance(input_body, str) else ""
    try:
        with trace_span("context.write", provider="dynamodb"):
            _dynamodb_client().put_item(
                TableName=table,
                Item={"user_phone_e164": {"S": user_phone}, "created_at": {"S": created_at}, "message_id": {"S": message_id}, "input_body": {"S": body}, "output_body": {"S": ""}, "ttl": {"N": str(int(time.time()) + CONTEXT_TTL_SECONDS)}},
                ConditionExpression="attribute_not_exists(user_phone_e164) AND attribute_not_exists(created_at)",
            )
        return True
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        LOGGER.info("message_context_write_failed phase=reserve error_type=%s", type(error).__name__)
        emit_event("context_write", "failure", outcome="storage_unavailable", metrics={"ContextWriteFailures": 1})
        return None
    except Exception as error:  # noqa: BLE001
        LOGGER.info("message_context_write_failed phase=reserve error_type=%s", type(error).__name__)
        emit_event("context_write", "failure", outcome="storage_unavailable", metrics={"ContextWriteFailures": 1})
        return None


def complete_interaction(user_phone: str, message_id: str, created_at: str, input_body: object, output_body: str) -> None:
    """Best-effort complete the reserved record without recording operational data."""
    table = context_table_name()
    if not table:
        return
    body = input_body if isinstance(input_body, str) else ""
    try:
        with trace_span("context.write", provider="dynamodb"):
            _dynamodb_client().put_item(
                TableName=table,
                Item={"user_phone_e164": {"S": user_phone}, "created_at": {"S": created_at}, "message_id": {"S": message_id}, "input_body": {"S": body}, "output_body": {"S": output_body}, "ttl": {"N": str(int(time.time()) + CONTEXT_TTL_SECONDS)}},
                ConditionExpression="message_id = :message_id",
                ExpressionAttributeValues={":message_id": {"S": message_id}},
            )
    except Exception as error:  # noqa: BLE001
        LOGGER.info("message_context_write_failed phase=complete error_type=%s", type(error).__name__)
        emit_event("context_write", "failure", outcome="storage_unavailable", metrics={"ContextWriteFailures": 1})


@lru_cache(maxsize=1)
def _dynamodb_client() -> Any:
    with trace_span("client.init", provider="dynamodb"):
        try:
            return boto3.client("dynamodb", config=Config(connect_timeout=2, read_timeout=2, retries={"mode": "standard", "max_attempts": 3}))
        except TypeError:
            return boto3.client("dynamodb")
