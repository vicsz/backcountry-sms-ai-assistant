from __future__ import annotations

from typing import Any

import pytest

from backcountry_sms import bedrock, context_store, handler, location


@pytest.mark.parametrize(
    ("factory", "module", "service"),
    [
        (bedrock._bedrock_client, bedrock, "bedrock-runtime"),
        (context_store._dynamodb_client, context_store, "dynamodb"),
        (location._amazon_places_client, location, "geo-places"),
        (handler._sms_client, handler, "pinpoint-sms-voice-v2"),
    ],
)
def test_aws_clients_are_reused_within_a_lambda_process(
    factory: Any, module: Any, service: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []

    def make_client(name: str, **_kwargs: object) -> object:
        assert name == service
        client = object()
        created.append(client)
        return client

    monkeypatch.setattr(module.boto3, "client", make_client)
    factory.cache_clear()
    try:
        first, second = factory(), factory()
        assert first is second
        assert len(created) == 1
    finally:
        factory.cache_clear()
