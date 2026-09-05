import json
import logging
from typing import Self
from urllib.parse import parse_qs, urlparse

import pytest
from botocore.exceptions import ClientError

from backcountry_sms import handler, retrieval

pytestmark = pytest.mark.legacy_python_runtime


def sns_event(sender: str, body: str = "tell me a joke", message_id: str = "test-message-id") -> dict:
    return {
        "Records": [
            {
                "Sns": {
                    "MessageId": message_id,
                    "Timestamp": "2026-08-29T12:00:00.000Z",
                    "Message": json.dumps(
                        {
                            "originationNumber": sender,
                            "destinationNumber": "stage-8-1-test-bot",
                            "messageBody": body,
                            "messageId": message_id,
                        }
                    )
                }
            }
        ]
    }


def stage_8_1_sns_event(body: str, message_id: str) -> dict:
    return sns_event("stage-8-1-test-sender", body, message_id)


class FakeBedrockClient:
    def __init__(
        self,
        response: dict | None = None,
        error: Exception | None = None,
        responses: list[dict] | None = None,
    ):
        self.calls: list[dict] = []
        self.response = response or {
            "output": {"message": {"content": [{"text": "A short joke."}]}}
        }
        self.error = error
        self.responses = responses or []

    def converse(self, **kwargs: object) -> dict:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        if self.responses:
            return self.responses.pop(0)
        if kwargs["system"][0]["text"] == handler.EXTRACTION_SYSTEM_PROMPT:  # type: ignore[index]
            return model_response('{"intent":"general","location_text":null,"current_location_text":"","coordinates":null,"time_window":"today","activity":"general","location_source":"none"}')
        return self.response


class FakeSmsClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send_text_message(self, **kwargs: str) -> None:
        self.calls.append(kwargs)


class FakeDynamoClient:
    def __init__(self, items: list[dict] | None = None, fail_query: bool = False, fail_put: bool = False) -> None:
        self.items = items or []
        self.fail_query, self.fail_put = fail_query, fail_put
        self.queries: list[dict] = []
        self.puts: list[dict] = []

    def query(self, **kwargs: object) -> dict:
        self.queries.append(kwargs)
        if self.fail_query:
            raise RuntimeError("unavailable")
        phone = kwargs["ExpressionAttributeValues"][":phone"]["S"]  # type: ignore[index]
        now = int(kwargs["ExpressionAttributeValues"][":now"]["N"])  # type: ignore[index]
        matches = [
            item for item in self.items
            if item["user_phone_e164"]["S"] == phone and int(item["ttl"]["N"]) > now and item.get("output_body", {}).get("S") is not None
        ]
        return {"Items": sorted(matches, key=lambda item: item["created_at"]["S"], reverse=True)[: kwargs["Limit"]]}  # type: ignore[index]

    def put_item(self, **kwargs: object) -> None:
        if self.fail_put:
            raise RuntimeError("unavailable")
        item = kwargs["Item"]  # type: ignore[assignment]
        if "ConditionExpression" in kwargs and "attribute_not_exists" in str(kwargs["ConditionExpression"]) and any(old["user_phone_e164"]["S"] == item["user_phone_e164"]["S"] and old["created_at"]["S"] == item["created_at"]["S"] for old in self.items):
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items = [old for old in self.items if not (old["user_phone_e164"]["S"] == item["user_phone_e164"]["S"] and old["created_at"]["S"] == item["created_at"]["S"])]
        self.items.append(item)
        self.puts.append(kwargs)


class PaginatedDynamoClient(FakeDynamoClient):
    def __init__(self, pages: list[dict]) -> None:
        super().__init__()
        self.pages = pages

    def query(self, **kwargs: object) -> dict:
        self.queries.append(kwargs)
        if not self.pages:
            return {"Items": []}
        return self.pages.pop(0)


class FakeWeatherResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _size: int) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def model_response(text: str) -> dict:
    return {"output": {"message": {"content": [{"text": text}]}}}


def hourly_payload() -> dict:
    return {
        "hourly": {
            "time": ["2026-08-30T18:00", "2026-08-31T09:00"],
            "temperature_2m": [8.0, 10.0],
            "precipitation_probability": [80, 10],
            "precipitation": [1.5, 0],
            "rain": [1.5, 0],
            "wind_speed_10m": [20, 10],
            "wind_gusts_10m": [42, 15],
            "weather_code": [61, 1],
        }
    }


def geonames_payload(name: str = "Burnt Island Lake") -> dict:
    return {
        "features": [
            {
                "geometry": {"type": "Point", "coordinates": [-78.6200, 45.6400]},
                "properties": {
                    "name": name,
                    "concise": "LAKE",
                    "location": "Nipissing, Ontario",
                    "relevance": 1000000,
                },
            }
        ]
    }


def configure(monkeypatch: pytest.MonkeyPatch, bedrock: FakeBedrockClient, dynamo: FakeDynamoClient | None = None) -> FakeSmsClient:
    sms = FakeSmsClient()
    monkeypatch.setenv("ALLOWED_PHONE_NUMBER", "test-allowed-sender")
    monkeypatch.setenv("ORIGINATION_IDENTITY", "test-origination-identity")
    monkeypatch.delenv("TEST_MODE", raising=False)
    monkeypatch.delenv("SMS_DELIVERY_MODE", raising=False)
    monkeypatch.delenv("DEPLOYMENT_ENVIRONMENT", raising=False)
    monkeypatch.setattr(handler.boto3, "client", lambda service: bedrock if service == "bedrock-runtime" else dynamo if service == "dynamodb" else sms)
    return sms


def test_capture_mode_logs_bounded_response_skips_sms_and_completes_context(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    bedrock = FakeBedrockClient()
    dynamo = FakeDynamoClient()
    sms = configure(monkeypatch, bedrock, dynamo)
    monkeypatch.setenv("MESSAGE_CONTEXT_TABLE", "test-context-table")
    monkeypatch.setenv("TEST_MODE", "true")
    monkeypatch.setenv("SMS_DELIVERY_MODE", "capture")
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", "test")

    result = handler.lambda_handler(sns_event("test-allowed-sender", message_id="stage-8-1-capture-001"), None)

    assert result == {"status": "captured", "delivery_mode": "capture", "sms_api_called": "false", "sns_published": "false"}
    assert sms.calls == []
    assert dynamo.items[0]["output_body"]["S"] == "A short joke."
    captured = next(record.message for record in caplog.records if "test_response_captured" in record.message)
    payload = json.loads(captured)
    assert payload == {"event": "test_response_captured", "test_run_id": "stage-8-1-capture-001", "delivery_mode": "capture", "response": "A short joke.", "sms_api_called": False, "sns_published": False}


def test_capture_mode_exercises_bedrock_location_weather_and_dynamo(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient(responses=[
        model_response('{"intent":"weather","location_text":"Burnt Island Lake, Algonquin","current_location_text":"Burnt Island Lake, Algonquin","coordinates":null,"time_window":"tomorrow","activity":"canoeing","location_source":"current"}'),
        model_response("Tomorrow: use caution on exposed water."),
    ])
    dynamo = FakeDynamoClient()
    sms = configure(monkeypatch, bedrock, dynamo)
    monkeypatch.setenv("MESSAGE_CONTEXT_TABLE", "test-context-table")
    monkeypatch.setenv("TEST_MODE", "true")
    monkeypatch.setenv("SMS_DELIVERY_MODE", "capture")
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", "test")

    def fake_urlopen(url: str, *, timeout: int) -> FakeWeatherResponse:
        assert timeout in {2, 3}
        return FakeWeatherResponse(geonames_payload() if url.startswith(handler.GEONAMES_API_URL) else hourly_payload())

    monkeypatch.setattr(handler, "urlopen", fake_urlopen)
    result = handler.lambda_handler(sns_event("test-allowed-sender", "Weather at Burnt Island Lake, Algonquin tomorrow", "stage-8-1-location-weather-001"), None)

    assert result["status"] == "captured"
    assert len(bedrock.calls) == 2
    assert len(dynamo.puts) == 2
    assert sms.calls == []


def configure_capture(monkeypatch: pytest.MonkeyPatch, bedrock: FakeBedrockClient, dynamo: FakeDynamoClient) -> FakeSmsClient:
    sms = configure(monkeypatch, bedrock, dynamo)
    monkeypatch.setenv("ALLOWED_PHONE_NUMBER", "stage-8-1-test-sender")
    monkeypatch.setenv("MESSAGE_CONTEXT_TABLE", "BackcountrySmsEchoTest-MessageContext")
    monkeypatch.setenv("TEST_MODE", "true")
    monkeypatch.setenv("SMS_DELIVERY_MODE", "capture")
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", "test")
    return sms


def rag_result(park: str, excerpt: str, source_url: str = "https://www.ontarioparks.ca/park/example", claims: tuple[tuple[str, str], ...] = ()) -> retrieval.RetrievalResult:
    return retrieval.RetrievalResult(excerpt, retrieval.RetrievalCitation(park, "Facilities", source_url), 0.9, claims)


@pytest.mark.parametrize(("question", "results", "answer", "source"), [
    ("Does the Portage Store area have canoe rentals?", [rag_result("Portage Store", "The Portage Store area lists canoe rentals and parking.")], "Canoe rentals are listed.", "Portage Store"),
    ("Does Killarney have backcountry camping?", [rag_result("Killarney", "Killarney lists backcountry camping.")], "Backcountry camping is listed.", "Killarney"),
    ("What should I know before visiting Algonquin based on the guide?", [rag_result("Algonquin Provincial Park", "Algonquin Provincial Park lists canoeing and backcountry camping.")], "Algonquin lists canoeing and backcountry camping.", "Algonquin"),
    ("What facilities are listed for Arrowhead?", [rag_result("Arrowhead", "Arrowhead lists canoe rentals and a boat launch.")], "Canoe rentals and a boat launch are listed.", "Arrowhead"),
    ("Are canoe rentals available at Arrowhead?", [rag_result("Arrowhead", "Arrowhead lists canoe rentals.")], "Canoe rentals are listed.", "Arrowhead"),
    ("Which Ontario parks mention canoeing and boat launches?", [rag_result("Arrowhead", "Arrowhead lists canoeing and a boat launch."), rag_result("Killarney", "Killarney lists canoeing and a boat launch.")], "Arrowhead and Killarney are listed.", "Arrowhead"),
])
def test_information_lookup_uses_one_retrieval_then_one_grounded_response(monkeypatch: pytest.MonkeyPatch, question: str, results: list[retrieval.RetrievalResult], answer: str, source: str) -> None:
    client = FakeBedrockClient(responses=[
        model_response('{"intent":"information_lookup","location_text":null,"current_location_text":"","coordinates":null,"time_window":"today","activity":"general","location_source":"none"}'),
        model_response(answer),
    ])
    local = retrieval.LocalRetriever(results)
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: local)
    monkeypatch.setattr(
        handler,
        "_bedrock_converse",
        lambda **kwargs: client.converse(system=[{"text": kwargs["system_prompt"]}])["output"]["message"]["content"][0]["text"],
    )
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_args: (_ for _ in ()).throw(AssertionError("weather called")))
    monkeypatch.setattr(handler, "_lookup_fire_ban", lambda *_args: (_ for _ in ()).throw(AssertionError("fire called")))
    monkeypatch.setattr(handler, "_resolve_named_place", lambda *_args: (_ for _ in ()).throw(AssertionError("location called")))

    response = handler._reply_for_message(question)

    assert local.questions == [question]
    assert len(client.calls) == 2
    assert source in response and "Source: Ontario Parks" in response
    assert "excerpts" in str(client.calls[1])


def test_information_lookup_accepts_null_unused_qualifiers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        handler,
        "_bedrock_converse",
        lambda **_kwargs: '{"intent":"information_lookup","location_text":null,"current_location_text":"","coordinates":null,"time_window":null,"activity":null,"location_source":"none"}',
    )

    context = handler._extract_weather_context("What facilities does Algonquin list?")

    assert context is not None
    assert context["intent"] == "information_lookup"
    assert context["time_window"] == "today"
    assert context["activity"] == "general"


def test_information_lookup_does_not_apply_weather_location_grounding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        handler,
        "_bedrock_converse",
        lambda **_kwargs: '{"intent":"information_lookup","location_text":"Algonquin Provincial Park","current_location_text":"Algonquin Provincial Park","coordinates":null,"time_window":"today","activity":"general","location_source":"current"}',
    )

    context = handler._extract_weather_context("What activities does Algonquin Provincial Park list?")

    assert context is not None
    assert context["intent"] == "information_lookup"
    assert context["location_text"] == "Algonquin Provincial Park"


@pytest.mark.parametrize("question", [
    "Is the park open tomorrow and are sites available?",
    "Is this trail currently closed?",
    "Can I make a reservation this weekend?",
])
def test_current_status_questions_redirect_without_model_or_retrieval(monkeypatch: pytest.MonkeyPatch, question: str) -> None:
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("model called")))
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: (_ for _ in ()).throw(AssertionError("retrieval called")))
    assert "check Ontario Parks directly" in handler._reply_for_message(question)


@pytest.mark.parametrize("question", [
    "What are the hours and prices at the Portage Store?",
    "Does this guide publish current Portage Store opening hours?",
])
def test_time_sensitive_guide_details_redirect_without_model_or_retrieval(monkeypatch: pytest.MonkeyPatch, question: str) -> None:
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("model called")))
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: (_ for _ in ()).throw(AssertionError("retrieval called")))
    response = handler._reply_for_message(question)
    assert "current park hours" in response


def test_enh_0001_current_news_explains_data_boundary_without_model_or_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("model called")))
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: (_ for _ in ()).throw(AssertionError("retrieval called")))

    response = handler._reply_for_message("What happened in Ontario today?")

    assert response == handler.CURRENT_DATA_LIMITATION_REPLY
    assert len(response) <= 160


def test_bug_0002_weather_dependent_crossing_bypasses_rag_after_misclassification(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handler, "_extract_weather_context", lambda *_args: {
        "intent": "information_lookup", "location_text": "Burnt Island Lake", "current_location_text": "",
        "coordinates": None, "time_window": "tomorrow", "activity": "general", "location_source": "history",
    })
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: (_ for _ in ()).throw(AssertionError("retrieval called")))
    monkeypatch.setattr(handler, "_weather_request_reply", lambda *_args: "weather path")

    assert handler._reply_for_message("We're planning a long crossing tomorrow morning. What should we watch for?") == "weather path"


def test_bug_0002_weather_activity_recovers_history_location_when_model_omits_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handler, "_extract_weather_context", lambda *_args: {
        "intent": "information_lookup", "location_text": "", "current_location_text": "",
        "coordinates": None, "time_window": "today", "activity": "general", "location_source": "none",
    })
    captured: list[dict[str, object]] = []

    def weather_path(_text: str, _coordinates: tuple[float, float] | None, _history: object, _readable: bool, context: dict[str, object]) -> str:
        captured.append(context)
        return "weather path"

    monkeypatch.setattr(handler, "_weather_request_reply", weather_path)
    history = [handler.ContextInteraction("We are at Burnt Island Lake today.", "Weather noted.", "prior")]

    assert handler._reply_for_message("We're planning a long crossing tomorrow morning. What should we watch for?", history) == "weather path"
    assert captured[0]["location_text"] == "Burnt Island Lake"
    assert captured[0]["location_source"] == "history"
    assert captured[0]["time_window"] == "tomorrow morning"
    assert captured[0]["activity"] == "open-water crossing"


def test_bug_0002_weather_activity_recovers_history_when_extraction_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handler, "_extract_weather_context", lambda *_args: None)
    captured: list[dict[str, object]] = []

    def weather_path(_text: str, _coordinates: tuple[float, float] | None, _history: object, _readable: bool, context: dict[str, object]) -> str:
        captured.append(context)
        return "weather path"

    monkeypatch.setattr(handler, "_weather_request_reply", weather_path)
    history = [handler.ContextInteraction("We are at Burnt Island Lake today.", "Weather noted.", "prior")]

    assert handler._reply_for_message("We're planning a long crossing tomorrow morning. What should we watch for?", history) == "weather path"
    assert captured[0]["location_text"] == "Burnt Island Lake"
    assert captured[0]["time_window"] == "tomorrow morning"


def test_bug_0002_rejects_absolute_safety_advice() -> None:
    assert handler._contains_absolute_safety_claim("Safe for paddling.")
    assert not handler._contains_absolute_safety_claim("Weather looks favorable; monitor conditions.")


def test_mixed_weather_and_current_site_status_redirects_before_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("model called")))
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: (_ for _ in ()).throw(AssertionError("retrieval called")))
    assert "check Ontario Parks directly" in handler._reply_for_message("What is the weather and are campsites available this weekend?")


def test_weekend_camping_availability_redirects_before_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("model called")))
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: (_ for _ in ()).throw(AssertionError("retrieval called")))
    assert "check Ontario Parks directly" in handler._reply_for_message("Can I camp at Killarney this weekend?")


@pytest.mark.parametrize(("question", "live_intent"), [
    ("What is the weather at Killarney?", "weather"),
    ("Is Killarney under a fire ban?", "fire_status"),
])
def test_weather_and_fire_never_enter_rag_after_extraction_misclassification(
    monkeypatch: pytest.MonkeyPatch, question: str, live_intent: str,
) -> None:
    monkeypatch.setattr(handler, "_extract_weather_context", lambda *_args: {
        "intent": "information_lookup", "location_text": "Killarney", "current_location_text": "",
        "coordinates": None, "time_window": "today", "activity": "general", "location_source": "none",
    })
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: (_ for _ in ()).throw(AssertionError("retrieval called")))
    if live_intent == "weather":
        monkeypatch.setattr(handler, "_weather_request_reply", lambda *_args: "weather path")
        assert handler._reply_for_message(question) == "weather path"
    else:
        monkeypatch.setattr(handler, "_fire_status_reply", lambda *_args: "fire path")
        assert handler._reply_for_message(question) == "fire path"


def test_rag_budget_fits_25_second_lambda_timeout() -> None:
    assert handler.RAG_WORST_CASE_SECONDS <= handler.RAG_LAMBDA_TIMEOUT_SECONDS
    assert handler.RAG_WORST_CASE_SECONDS == 17


def test_stable_facility_availability_does_not_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    local = retrieval.LocalRetriever([rag_result("Arrowhead", "Arrowhead lists canoe rentals.")])
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: local)
    monkeypatch.setattr(handler, "_extract_weather_context", lambda *_args: {
        "intent": "information_lookup", "location_text": "", "current_location_text": "", "coordinates": None,
        "time_window": "today", "activity": "general", "location_source": "none",
    })
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: "Canoe rentals are listed.")

    response = handler._reply_for_message("Are canoe rentals available at Arrowhead?")

    assert local.questions == ["Are canoe rentals available at Arrowhead?"]
    assert "Source: Ontario Parks" in response


@pytest.mark.parametrize("local", [
    retrieval.LocalRetriever(),
    retrieval.LocalRetriever([
        rag_result("NeverListed Park", "Winter camping is listed.", claims=(("winter_camping", "yes"),)),
        rag_result("NeverListed Park", "Winter camping is not listed.", claims=(("winter_camping", "no"),)),
    ]),
    retrieval.LocalRetriever(error=retrieval.RetrievalFailure("timeout")),
])
def test_information_lookup_unusable_evidence_never_calls_uncited_model(monkeypatch: pytest.MonkeyPatch, local: retrieval.LocalRetriever) -> None:
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: local)
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("response model called")))
    response = handler._information_lookup_reply("Does NeverListed Park have winter camping?")
    assert "Ontario Parks" in response


def test_information_lookup_rejects_generic_hit_for_unknown_named_park(monkeypatch: pytest.MonkeyPatch) -> None:
    local = retrieval.LocalRetriever([rag_result("Arrowhead", "Arrowhead lists canoe rentals.")])
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: local)
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("response model called")))

    response = handler._information_lookup_reply("Does NeverListed Park have winter camping?")

    assert "does not establish" in response


@pytest.mark.parametrize("answer", ["", "Arrowhead is open today.", "Arrowhead has a marina and beach."])
def test_information_lookup_rejects_empty_current_or_ungrounded_model_answer(monkeypatch: pytest.MonkeyPatch, answer: str) -> None:
    local = retrieval.LocalRetriever([rag_result("Arrowhead", "Arrowhead lists canoe rentals and a boat launch.")])
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: local)
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: answer)

    response = handler._information_lookup_reply("What facilities are listed for Arrowhead?")

    assert response == "The Ontario Parks guide does not establish that answer. Please check Ontario Parks directly."


def test_information_lookup_requires_a_source_before_model_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    local = retrieval.LocalRetriever([rag_result("Arrowhead", "Arrowhead lists canoe rentals.", source_url="")])
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: local)
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("model called")))

    assert "does not establish" in handler._information_lookup_reply("What facilities are listed for Arrowhead?")


def test_information_lookup_requires_a_citation_for_each_result(monkeypatch: pytest.MonkeyPatch) -> None:
    local = retrieval.LocalRetriever([
        rag_result("Arrowhead", "Arrowhead lists canoeing and a boat launch."),
        rag_result("Killarney", "Killarney lists canoeing.", source_url=""),
    ])
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: local)
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("model called")))
    assert "does not establish" in handler._information_lookup_reply("Which parks mention canoeing?")


def test_unmarked_contradictory_fixture_results_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    local = retrieval.LocalRetriever([
        rag_result("Algonquin", "Algonquin lists backcountry camping."),
        rag_result("Algonquin", "Algonquin does not list backcountry camping."),
    ])
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: local)
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("model called")))
    assert "does not establish" in handler._information_lookup_reply("Does Algonquin have backcountry camping?")


def test_grounded_answer_cannot_reverse_explicit_negation(monkeypatch: pytest.MonkeyPatch) -> None:
    local = retrieval.LocalRetriever([rag_result("Algonquin", "Algonquin does not list backcountry camping.")])
    monkeypatch.setattr(handler.retrieval, "configured_retriever", lambda: local)
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: "Backcountry camping is listed.")
    assert "does not establish" in handler._information_lookup_reply("Does Algonquin have backcountry camping?")


def test_capture_follow_up_isolated_from_production_sender_history(monkeypatch: pytest.MonkeyPatch) -> None:
    production_history = {"user_phone_e164": {"S": "production-test-sender"}, "created_at": {"S": "2026-08-31T11:00:00Z"}, "input_body": {"S": "Toronto"}, "output_body": {"S": "Production-only context"}, "ttl": {"N": "9999999999"}}
    dynamo = FakeDynamoClient(items=[production_history])
    bedrock = FakeBedrockClient(responses=[
        model_response('{"intent":"weather","location_text":null,"current_location_text":"","coordinates":null,"time_window":"today","activity":"general","location_source":"history"}'),
        model_response("Captured test follow-up."),
    ])
    sms = configure_capture(monkeypatch, bedrock, dynamo)

    result = handler.lambda_handler(stage_8_1_sns_event("What about tomorrow?", "stage-8-1-follow-up-001"), None)

    assert result["status"] == "captured"
    assert dynamo.queries[0]["ExpressionAttributeValues"][":phone"]["S"] == "stage-8-1-test-sender"
    assert "Production-only context" not in str(bedrock.calls[0])
    assert sms.calls == []


def test_capture_duplicate_id_is_ignored_without_second_provider_or_sms_call(monkeypatch: pytest.MonkeyPatch) -> None:
    dynamo = FakeDynamoClient()
    bedrock = FakeBedrockClient()
    sms = configure_capture(monkeypatch, bedrock, dynamo)
    event = stage_8_1_sns_event("tell me a joke", "stage-8-1-duplicate-001")

    assert handler.lambda_handler(event, None)["status"] == "captured"
    assert handler.lambda_handler(event, None) == {"status": "ignored", "reason": "duplicate_delivery"}
    assert len(bedrock.calls) == 2
    assert sms.calls == []


def test_invalid_delivery_configuration_fails_before_storage_or_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    dynamo = FakeDynamoClient()
    bedrock = FakeBedrockClient()
    sms = configure(monkeypatch, bedrock, dynamo)
    monkeypatch.setenv("ALLOWED_PHONE_NUMBER", "stage-8-1-test-sender")
    monkeypatch.setenv("TEST_MODE", "false")
    monkeypatch.setenv("SMS_DELIVERY_MODE", "capture")
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="capture_mode_not_permitted"):
        handler.lambda_handler(stage_8_1_sns_event("tell me a joke", "stage-8-1-invalid-config-001"), None)
    assert bedrock.calls == []
    assert dynamo.queries == []
    assert dynamo.puts == []
    assert sms.calls == []


@pytest.mark.parametrize(("test_mode", "delivery_mode", "environment"), [("false", "capture", "production"), ("true", "capture", "production"), ("true", "live", "test"), ("maybe", "live", "production")])
def test_delivery_configuration_fails_closed(monkeypatch: pytest.MonkeyPatch, test_mode: str, delivery_mode: str, environment: str) -> None:
    monkeypatch.setenv("TEST_MODE", test_mode)
    monkeypatch.setenv("SMS_DELIVERY_MODE", delivery_mode)
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", environment)

    with pytest.raises(RuntimeError):
        handler._delivery_mode()


def test_live_mode_preserves_sender_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient()
    sms = configure(monkeypatch, bedrock)
    handler.lambda_handler(sns_event("test-allowed-sender"), None)
    assert sms.calls[0]["DestinationPhoneNumber"] == "test-allowed-sender"
    assert sms.calls[0]["OriginationIdentity"] == "test-origination-identity"


def test_allowed_sender_uses_bedrock_and_sends_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient()
    sms = configure(monkeypatch, bedrock)

    assert handler.lambda_handler(sns_event("test-allowed-sender"), None) == {
        "status": "replied"
    }
    assert len(bedrock.calls) == 2
    assert bedrock.calls[0]["modelId"] == handler.DEFAULT_MODEL_ID
    assert bedrock.calls[0]["inferenceConfig"]["maxTokens"] == 80
    assert "Classify every message" in bedrock.calls[0]["system"][0]["text"]
    assert bedrock.calls[1]["inferenceConfig"]["maxTokens"] == 128
    assert "Use HISTORY as conversational context" in bedrock.calls[1]["system"][0]["text"]
    assert sms.calls[0]["MessageBody"] == "A short joke."


def test_allowed_sender_uses_explicit_test_model_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient()
    configure(monkeypatch, bedrock)
    monkeypatch.setenv("BEDROCK_MODEL_ID", "us.amazon.nova-micro-v1:0")

    handler.lambda_handler(sns_event("test-allowed-sender", "hello"), None)

    assert [call["modelId"] for call in bedrock.calls] == ["us.amazon.nova-micro-v1:0"] * 2


def test_arbitrary_message_is_sent_to_bedrock(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient()
    configure(monkeypatch, bedrock)

    handler.lambda_handler(sns_event("test-allowed-sender", "hello"), None)

    payload = json.loads(bedrock.calls[0]["messages"][0]["content"][0]["text"])
    assert payload["current_sms"] == "hello"
    assert payload["history"] == []


def test_long_model_output_is_limited_to_one_sms_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    long_text = "x" * 300
    bedrock = FakeBedrockClient(
        {"output": {"message": {"content": [{"text": long_text}]}}}
    )
    sms = configure(monkeypatch, bedrock)

    handler.lambda_handler(sns_event("test-allowed-sender"), None)

    assert len(sms.calls[0]["MessageBody"]) == handler.MAX_SMS_CHARS


def test_model_failure_sends_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient(error=RuntimeError("unavailable"))
    sms = configure(monkeypatch, bedrock)

    handler.lambda_handler(sns_event("test-allowed-sender"), None)

    assert sms.calls[0]["MessageBody"] == handler.WEATHER_EXTRACTION_FALLBACK


def test_account_verification_error_has_clear_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = ClientError(
        {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "Your account is currently being verified.",
            }
        },
        "Converse",
    )
    bedrock = FakeBedrockClient(error=error)
    sms = configure(monkeypatch, bedrock)

    handler.lambda_handler(sns_event("test-allowed-sender"), None)

    assert sms.calls[0]["MessageBody"] == handler.WEATHER_EXTRACTION_FALLBACK


def test_throttled_error_has_retry_message(monkeypatch: pytest.MonkeyPatch) -> None:
    error = ClientError({"Error": {"Code": "ThrottlingException"}}, "Converse")
    bedrock = FakeBedrockClient(error=error)
    sms = configure(monkeypatch, bedrock)

    handler.lambda_handler(sns_event("test-allowed-sender"), None)

    assert sms.calls[0]["MessageBody"] == handler.WEATHER_EXTRACTION_FALLBACK


def test_unapproved_sender_does_not_call_bedrock_or_send_sms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bedrock = FakeBedrockClient()
    sms = configure(monkeypatch, bedrock)

    assert handler.lambda_handler(sns_event("test-unapproved-sender"), None) == {
        "status": "ignored",
        "reason": "sender_not_allowed",
    }
    assert bedrock.calls == []
    assert sms.calls == []


def test_coordinate_weather_uses_exact_coordinates_and_two_bedrock_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":null,"current_location_text":"","coordinates":{"latitude":45.62,"longitude":-78.42},"time_window":"tonight","activity":"canoeing","location_source":"current"}'),
            model_response("Rain likely tonight; set the tarp and avoid open-water canoeing."),
        ]
    )
    sms = configure(monkeypatch, bedrock)
    urls: list[str] = []

    def fake_urlopen(url: str, *, timeout: int) -> FakeWeatherResponse:
        assert timeout == 3
        urls.append(url)
        return FakeWeatherResponse(hourly_payload())

    monkeypatch.setattr(handler, "urlopen", fake_urlopen)

    handler.lambda_handler(
        sns_event("test-allowed-sender", "Canoe tonight at lat 45.6200; lon -78.4200"),
        None,
    )

    assert len(bedrock.calls) == 2
    advice_payload = json.loads(json.loads(bedrock.calls[1]["messages"][0]["content"][0]["text"])["current_sms"])
    assert advice_payload["location"] == {"label": "provided GPS coordinates", "coordinates": {"latitude": 45.62, "longitude": -78.42}}
    query = parse_qs(urlparse(urls[0]).query)
    assert query["latitude"] == ["45.620000"]
    assert query["longitude"] == ["-78.420000"]
    synthesis_payload = bedrock.calls[1]["messages"][0]["content"][0]["text"]
    assert "Avoid open-water canoeing" in synthesis_payload
    assert "avoid open-water" in sms.calls[0]["MessageBody"].lower()


def test_coordinate_cleanup_accepts_labels_and_separators() -> None:
    assert handler._parse_coordinates("weather lat=45.62 / lon=-78.42") == (45.62, -78.42)
    assert handler._parse_coordinates("weather at 45.62 N, 78.42 W") == (45.62, -78.42)
    assert handler._parse_coordinates("weather at 45.62°N; 78.42°W") == (45.62, -78.42)
    assert handler._parse_coordinates("weather at -45.62 N, 78.42 W") is None
    assert handler._parse_coordinates("weather 91,-78.42") is None
    assert handler._parse_coordinates("weather in Algonquin") is None


def test_named_lake_uses_only_provider_coordinates_then_stage_three_weather(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Burnt Island Lake, Algonquin","current_location_text":"Burnt Island Lake, Algonquin","coordinates":null,"time_window":"tomorrow","activity":"canoeing","location_source":"current"}'),
            model_response("Tomorrow: use caution on exposed water."),
        ]
    )
    sms = configure(monkeypatch, bedrock)
    urls: list[str] = []

    def fake_urlopen(url: str, *, timeout: int) -> FakeWeatherResponse:
        urls.append(url)
        if url.startswith(handler.GEONAMES_API_URL):
            return FakeWeatherResponse(geonames_payload())
        return FakeWeatherResponse(hourly_payload())

    monkeypatch.setattr(handler, "urlopen", fake_urlopen)

    handler.lambda_handler(
        sns_event("test-allowed-sender", "Weather at Burnt Island Lake, Algonquin tomorrow"),
        None,
    )

    assert len(bedrock.calls) == 2
    assert len(urls) == 2
    weather_query = parse_qs(urlparse(urls[1]).query)
    assert weather_query["latitude"] == ["45.640000"]
    assert weather_query["longitude"] == ["-78.620000"]
    assert sms.calls[0]["MessageBody"] == "Tomorrow: use caution on exposed water."


def test_named_place_not_found_requests_gps_without_weather_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Unknown Lake","current_location_text":"Unknown Lake","coordinates":null,"time_window":"tonight","activity":"camping","location_source":"current"}'),
            model_response(handler.WEATHER_LOCATION_NOT_FOUND),
        ]
    )
    sms = configure(monkeypatch, bedrock)
    history = [handler.ContextInteraction("Weather at Toronto", "Toronto: rain tonight.", "prior")]
    monkeypatch.setattr(handler, "_load_context", lambda _phone: (history, True))
    monkeypatch.setattr(handler, "_search_canadian_geonames", lambda _query: [])
    monkeypatch.setattr(handler, "_search_amazon_places", lambda _query: [])

    handler.lambda_handler(sns_event("test-allowed-sender", "Weather at Unknown Lake tonight"), None)

    assert sms.calls[0]["MessageBody"] == handler.WEATHER_LOCATION_NOT_FOUND
    assert len(bedrock.calls) == 2
    fallback = json.loads(bedrock.calls[1]["messages"][0]["content"][0]["text"])
    assert fallback["current_sms"] == "Weather at Unknown Lake tonight"
    assert fallback["history"] == [{"input": "Weather at Toronto", "output": "Toronto: rain tonight."}]


def test_named_location_provider_failure_still_makes_bounded_second_response(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Portage Store","current_location_text":"Portage Store","coordinates":null,"time_window":"today","activity":"general","location_source":"current"}'),
            model_response(handler.WEATHER_LOCATION_UNAVAILABLE),
        ]
    )
    sms = configure(monkeypatch, bedrock)
    history = [handler.ContextInteraction("Weather at Toronto", "Toronto: rain tonight.", "prior")]
    monkeypatch.setattr(handler, "_load_context", lambda _phone: (history, True))
    monkeypatch.setattr(handler, "_search_canadian_geonames", lambda _query: (_ for _ in ()).throw(OSError("down")))
    monkeypatch.setattr(handler, "_search_amazon_places", lambda _query: (_ for _ in ()).throw(OSError("down")))

    handler.lambda_handler(sns_event("test-allowed-sender", "Portage Store conditions?"), None)

    assert sms.calls[0]["MessageBody"] == handler.WEATHER_LOCATION_UNAVAILABLE
    assert len(bedrock.calls) == 2
    assert bedrock.calls[1]["system"][0]["text"] == handler.LOCATION_REQUEST_SYSTEM_PROMPT
    fallback = json.loads(bedrock.calls[1]["messages"][0]["content"][0]["text"])
    assert fallback["current_sms"] == "Portage Store conditions?"
    assert fallback["history"] == [{"input": "Weather at Toronto", "output": "Toronto: rain tonight."}]


def test_ambiguous_distant_provider_candidates_require_clarification() -> None:
    candidates = [
        handler.LocationCandidate("Pine Lake", 45.0, -78.0, "LAKE", "Ontario", "nrcan_geonames"),
        handler.LocationCandidate("Pine Lake", 50.0, -85.0, "LAKE", "Ontario", "nrcan_geonames"),
    ]

    resolution = handler._rank_location_candidates("Pine Lake", candidates)

    assert resolution.candidate is None
    assert resolution.outcome == "ambiguous"


def test_amazon_places_candidate_requires_provider_coordinates(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePlacesClient:
        def search_text(self, **kwargs: object) -> dict:
            assert kwargs["Filter"] == {"IncludeCountries": ["CAN", "USA"]}
            return {
                "ResultItems": [
                    {
                        "Title": "Canoe Lake Access Point (The Portage Store)",
                        "Position": [-78.70812, 45.53525],
                        "Categories": [{"Name": "Sporting Goods Store"}],
                        "Address": {
                            "Region": {"Name": "Ontario"},
                            "Country": {"Code3": "CAN"},
                        },
                    }
                ]
            }

    monkeypatch.setattr(handler.boto3, "client", lambda service, **_kwargs: FakePlacesClient())

    candidates = handler._search_amazon_places("Portage Store")

    assert candidates == [
        handler.LocationCandidate(
            "Canoe Lake Access Point (The Portage Store)",
            45.53525,
            -78.70812,
            "Sporting Goods Store",
            "Ontario CAN",
            "amazon_location_places",
        )
    ]


def test_portage_store_resolves_from_amazon_provider_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = handler.LocationCandidate(
        "Canoe Lake Access Point (The Portage Store)",
        45.53525,
        -78.70812,
        "Sporting Goods Store",
        "Ontario CAN",
        "amazon_location_places",
    )
    monkeypatch.setattr(handler, "_search_canadian_geonames", lambda _query: [])
    monkeypatch.setattr(handler, "_search_amazon_places", lambda _query: [candidate])

    resolution = handler._resolve_named_place("Portage Store")

    assert resolution.candidate == candidate
    assert resolution.outcome == "resolved"


def test_abbreviated_us_city_matches_provider_name() -> None:
    candidate = handler.LocationCandidate(
        "New York City",
        40.7128,
        -74.0060,
        "CITY",
        "New York USA",
        "amazon_location_places",
    )

    resolution = handler._rank_location_candidates("NYC", [candidate])

    assert resolution.candidate == candidate
    assert resolution.outcome == "resolved"


def test_bug_0001_unqualified_common_place_prefers_ontario_candidate() -> None:
    ontario = handler.LocationCandidate(
        "Collingwood", 44.50, -80.22, "CITY", "Collingwood, Ontario, Canada", "amazon_location_places", score=80
    )
    pennsylvania = handler.LocationCandidate(
        "Collingwood", 40.12, -75.01, "CITY", "Pennsylvania, USA", "amazon_location_places", score=100
    )

    resolution = handler._rank_location_candidates("Collingwood", [pennsylvania, ontario])

    assert resolution.outcome == "resolved"
    assert resolution.candidate == ontario


def test_missing_location_calls_interpreter_but_not_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":null,"current_location_text":"","coordinates":null,"time_window":"tonight","activity":"camping","location_source":"none"}'),
            model_response(handler.WEATHER_LOCATION_PROMPT),
        ]
    )
    sms = configure(monkeypatch, bedrock)

    handler.lambda_handler(sns_event("test-allowed-sender", "Will we need the tarp tonight?"), None)

    assert sms.calls[0]["MessageBody"] == handler.WEATHER_LOCATION_PROMPT
    assert len(bedrock.calls) == 2
    assert bedrock.calls[1]["system"][0]["text"] == handler.LOCATION_REQUEST_SYSTEM_PROMPT


def test_natural_toronto_location_comes_from_interpreter_not_phrase_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Toronto","current_location_text":"Toronto","coordinates":null,"time_window":"now","activity":"general","location_source":"current"}'),
            model_response("Toronto conditions are mild. Keep a light layer handy."),
        ]
    )
    sms = configure(monkeypatch, bedrock)
    captured: list[str] = []
    candidate = handler.LocationCandidate("Toronto", 43.65, -79.38, "CITY", "Ontario", "amazon_location_places")
    monkeypatch.setattr(handler, "_resolve_named_place", lambda query: (captured.append(query) or handler.LocationResolution(candidate, "resolved")))
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_coords: handler._normalize_hourly_weather(hourly_payload()))

    handler.lambda_handler(sns_event("test-allowed-sender", "I'm in Toronto now ... what's the weather"), None)

    assert captured == ["Toronto"]
    assert len(bedrock.calls) == 2
    assert "at|in|near" not in handler.EXTRACTION_SYSTEM_PROMPT
    assert "Toronto conditions" in sms.calls[0]["MessageBody"]


def test_bug_0001_collingwood_named_location_reaches_provider_backed_weather_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Collingwood","current_location_text":"Collingwood","coordinates":null,"time_window":"tonight","activity":"general","location_source":"current"}'),
            model_response("Collingwood conditions are mild tonight."),
        ]
    )
    sms = configure(monkeypatch, bedrock)
    candidate = handler.LocationCandidate("Collingwood", 44.50, -80.22, "CITY", "Ontario, Canada", "nrcan_geonames")
    captured: list[str] = []
    monkeypatch.setattr(handler, "_resolve_named_place", lambda query: (captured.append(query) or handler.LocationResolution(candidate, "resolved")))
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_coords: handler._normalize_hourly_weather(hourly_payload()))

    handler.lambda_handler(sns_event("test-allowed-sender", "Weather in Collingwood this evening"), None)

    assert captured == ["Collingwood"]
    assert sms.calls[0]["MessageBody"] == "Collingwood conditions are mild tonight."


def test_bug_0001_interpreter_prompt_sets_canada_ontario_named_place_defaults() -> None:
    prompt = handler.EXTRACTION_SYSTEM_PROMPT.casefold()

    assert "assume canada" in prompt
    assert "prefer ontario" in prompt
    assert "collingwood" in prompt
    assert "popularity/relevance" in prompt
    assert "weather in collingwood this evening" in prompt
    assert "time_window 'evening'" in prompt


def test_bug_0001_current_grounded_location_can_fill_omitted_redundant_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interpretation = '{"intent":"weather","location_text":"Collingwood","current_location_text":"","coordinates":null,"time_window":"evening","activity":"general","location_source":"current"}'
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: interpretation)

    context = handler._extract_weather_context("Weather in Collingwood this evening")

    assert context is not None
    assert context["location_text"] == "Collingwood"
    assert context["current_location_text"] == "Collingwood"


def test_bug_0002_prompt_routes_weather_dependent_outdoor_decisions() -> None:
    prompt = handler.EXTRACTION_SYSTEM_PROMPT.casefold()
    advice_prompt = handler.ADVICE_SYSTEM_PROMPT.casefold()

    assert "outdoor activity" in prompt
    assert "weather would materially help" in prompt
    assert "cross this lake at noon" in prompt
    assert "put the tarp up before bed" in prompt
    assert "never guarantee that an activity is safe" in advice_prompt


def test_bug_0002_history_location_with_qualifier_is_canonicalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interpretation = '{"intent":"weather","location_text":"Burnt Island Lake, Algonquin","current_location_text":"","coordinates":null,"time_window":"noon","activity":"open-water crossing","location_source":"history"}'
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: interpretation)
    history = [handler.ContextInteraction("We are at Burnt Island Lake today.", "Weather noted.", "prior")]

    context = handler._extract_weather_context("Can I safely cross this lake at noon?", history)

    assert context is not None
    assert context["location_text"] == "Burnt Island Lake"
    assert context["location_source"] == "history"


def test_bug_0002_deictic_history_location_uses_newest_grounded_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interpretation = '{"intent":"weather","location_text":"the lake","current_location_text":"","coordinates":null,"time_window":"noon","activity":"open-water crossing","location_source":"history"}'
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: interpretation)
    history = [handler.ContextInteraction("We are at Burnt Island Lake today.", "Weather noted.", "prior")]

    context = handler._extract_weather_context("Can I safely cross this lake at noon?", history)

    assert context is not None
    assert context["location_text"] == "Burnt Island Lake"
    assert context["location_source"] == "history"


def test_bug_0002_history_follow_up_discards_inherited_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interpretation = '{"intent":"weather","location_text":"Burnt Island Lake","current_location_text":"","coordinates":{"latitude":45.62,"longitude":-78.42},"time_window":"overnight","activity":"camping","location_source":"history"}'
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: interpretation)
    history = [handler.ContextInteraction("We are at Burnt Island Lake today.", "Weather noted.", "prior")]

    context = handler._extract_weather_context("Should I put the tarp up before bed?", history)

    assert context is not None
    assert context["location_text"] == "Burnt Island Lake"
    assert context["coordinates"] is None


def test_bug_0002_model_current_label_is_downgraded_to_grounded_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interpretation = '{"intent":"weather","location_text":"Burnt Island Lake","current_location_text":"Burnt Island Lake","coordinates":null,"time_window":"overnight","activity":"camping","location_source":"current"}'
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: interpretation)
    history = [handler.ContextInteraction("We are at Burnt Island Lake today.", "Weather noted.", "prior")]

    context = handler._extract_weather_context("Should I put the tarp up before bed?", history)

    assert context is not None
    assert context["location_text"] == "Burnt Island Lake"
    assert context["current_location_text"] == ""
    assert context["location_source"] == "history"


def test_llm_weather_intent_routes_natural_wording_without_weather_keywords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Toronto","current_location_text":"Toronto","coordinates":null,"time_window":"now","activity":"general","location_source":"current"}'),
            model_response("Toronto conditions are mild. Keep a light layer handy."),
        ]
    )
    configure(monkeypatch, bedrock)
    candidate = handler.LocationCandidate("Toronto", 43.65, -79.38, "CITY", "Ontario", "amazon_location_places")
    resolved: list[str] = []
    monkeypatch.setattr(handler, "_resolve_named_place", lambda query: (resolved.append(query) or handler.LocationResolution(candidate, "resolved")))
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_coords: handler._normalize_hourly_weather(hourly_payload()))

    handler.lambda_handler(sns_event("test-allowed-sender", "Are conditions okay in Toronto right now?"), None)

    assert resolved == ["Toronto"]
    assert len(bedrock.calls) == 2


def test_interpreter_cleans_portage_store_filler(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Portage Store","current_location_text":"Portage Store","coordinates":null,"time_window":"tomorrow","activity":"canoeing","location_source":"current"}'),
            model_response("Tomorrow: check wind before paddling."),
        ]
    )
    sms = configure(monkeypatch, bedrock)
    captured: list[str] = []
    candidate = handler.LocationCandidate("Portage Store", 45.5, -78.7, "STORE", "Ontario", "amazon_location_places")
    monkeypatch.setattr(handler, "_resolve_named_place", lambda query: (captured.append(query) or handler.LocationResolution(candidate, "resolved")))
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_coords: handler._normalize_hourly_weather(hourly_payload()))

    handler.lambda_handler(sns_event("test-allowed-sender", "Currently near the Portage Store, forecast tomorrow?"), None)

    assert captured == ["Portage Store"]
    assert sms.calls[0]["MessageBody"] == "Tomorrow: check wind before paddling."


def test_current_location_wins_over_history_from_interpreter(monkeypatch: pytest.MonkeyPatch) -> None:
    history = [handler.ContextInteraction("Weather at Old Lake", "old", "a")]
    captured: list[str] = []
    candidate = handler.LocationCandidate("New Lake", 45.0, -78.0, "LAKE", "Ontario", "nrcan_geonames")
    monkeypatch.setattr(
        handler,
        "_extract_weather_context",
        lambda *_args: {"intent": "weather", "location_text": "New Lake", "coordinates": None, "time_window": "today", "activity": "general", "location_source": "current"},
    )
    monkeypatch.setattr(handler, "_resolve_named_place", lambda query: (captured.append(query) or handler.LocationResolution(candidate, "resolved")))
    monkeypatch.setattr(handler, "_weather_reply", lambda *_args: "ok")

    assert handler._reply_for_message("Weather in New Lake", history) == "ok"
    assert captured == ["New Lake"]


def test_toronto_current_location_overrides_historical_place(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: do not use Pine Ridge when the interpreter selects current Toronto."""
    history = [handler.ContextInteraction("Weather at Pine Ridge", "old weather", "a")]
    candidate = handler.LocationCandidate("Toronto", 43.65, -79.38, "CITY", "Ontario", "amazon_location_places")
    monkeypatch.setattr(
        handler,
        "_extract_weather_context",
        lambda *_args: {"intent": "weather", "location_text": "Toronto", "coordinates": None, "time_window": "now", "activity": "general", "location_source": "current"},
    )
    resolved: list[str] = []
    monkeypatch.setattr(handler, "_resolve_named_place", lambda query: (resolved.append(query) or handler.LocationResolution(candidate, "resolved")))
    monkeypatch.setattr(handler, "_weather_reply", lambda *_args: "Toronto weather")

    assert handler._reply_for_message("I'm in Toronto now... what's the weather?", history) == "Toronto weather"
    assert resolved == ["Toronto"]
    assert "CURRENT SMS always wins" in handler.EXTRACTION_SYSTEM_PROMPT
    assert "location_text Toronto" in handler.EXTRACTION_SYSTEM_PROMPT


def test_current_location_model_result_overrides_stale_history(monkeypatch: pytest.MonkeyPatch) -> None:
    history = [handler.ContextInteraction("Weather at Pine Ridge", "old weather", "a")]
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Toronto","current_location_text":"Toronto","coordinates":null,"time_window":"now","activity":"general","location_source":"current"}'),
            model_response("Toronto conditions are mild."),
        ]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)
    candidate = handler.LocationCandidate("Toronto", 43.65, -79.38, "CITY", "Ontario", "amazon_location_places")
    resolved: list[str] = []
    monkeypatch.setattr(handler, "_resolve_named_place", lambda query: (resolved.append(query) or handler.LocationResolution(candidate, "resolved")))
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_coords: handler._normalize_hourly_weather(hourly_payload()))

    assert handler._reply_for_message("I'm in Toronto now. How are conditions?", history) == "Toronto conditions are mild."
    assert resolved == ["Toronto"]
    envelope = json.loads(bedrock.calls[0]["messages"][0]["content"][0]["text"])
    assert envelope["current_sms"] == "I'm in Toronto now. How are conditions?"
    assert envelope["history"][0]["input"] == "Weather at Pine Ridge"
    advice_envelope = json.loads(bedrock.calls[1]["messages"][0]["content"][0]["text"])
    assert advice_envelope["history"] == [{"input": "Weather at Pine Ridge", "output": "old weather"}]


def test_current_whereabouts_supply_weather_location_when_question_follows_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = [handler.ContextInteraction("Weather at Pine Ridge", "old weather", "prior")]
    bedrock = FakeBedrockClient(
        responses=[
            model_response(
                '{"intent":"weather","location_text":"Toronto","current_location_text":"Toronto",'
                '"coordinates":null,"time_window":"now","activity":"general","location_source":"current"}'
            ),
            model_response("Toronto conditions are mild."),
        ]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)
    candidate = handler.LocationCandidate("Toronto", 43.65, -79.38, "CITY", "Ontario", "amazon_location_places")
    resolved: list[str] = []
    monkeypatch.setattr(
        handler,
        "_resolve_named_place",
        lambda query: (resolved.append(query) or handler.LocationResolution(candidate, "resolved")),
    )
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_coords: handler._normalize_hourly_weather(hourly_payload()))

    reply = handler._reply_for_message("I'm in Toronto now, what's the weather?", history)

    assert reply == "Toronto conditions are mild."
    assert resolved == ["Toronto"]
    assert "where the user is" in handler.EXTRACTION_SYSTEM_PROMPT


def test_interpretation_logs_only_the_location_source(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    history = [handler.ContextInteraction("Weather at Pine Ridge", "old", "a")]
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Toronto","current_location_text":"Toronto","coordinates":null,"time_window":"now","activity":"general","location_source":"current"}'),
            model_response('{"intent":"weather","location_text":"Pine Ridge","current_location_text":"","coordinates":null,"time_window":"tomorrow","activity":"general","location_source":"history"}'),
        ]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)

    with caplog.at_level(logging.INFO, logger=handler.__name__):
        assert handler._extract_weather_context("Toronto conditions now?", history) is not None
        assert handler._extract_weather_context("What about tomorrow?", history) is not None

    source_events = [record.getMessage() for record in caplog.records if record.getMessage().startswith("interpretation_location_source")]
    assert source_events == ["interpretation_location_source source=current", "interpretation_location_source source=history"]
    assert all("Toronto" not in event and "Pine Ridge" not in event for event in source_events)


@pytest.mark.parametrize(
    "interpretation",
    [
        '{"intent":"weather","location_text":null,"current_location_text":"","time_window":"today","activity":"general","location_source":"none"}',
        '{"intent":"weather","location_text":null,"current_location_text":"","coordinates":null,"activity":"general","location_source":"none"}',
        '{"intent":"general","location_text":null,"current_location_text":"","coordinates":null,"time_window":"today","activity":null,"location_source":"none"}',
        '{"intent":"weather","location_text":null,"current_location_text":"","coordinates":null,"time_window":{},"activity":"general","location_source":"none"}',
    ],
)
def test_interpretation_rejects_missing_or_non_string_required_fields(monkeypatch: pytest.MonkeyPatch, interpretation: str) -> None:
    bedrock = FakeBedrockClient(responses=[model_response(interpretation)])
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)

    assert handler._extract_weather_context("What's the weather?") is None


def test_interpretation_defaults_null_weather_qualifiers(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient(responses=[model_response(
        '{"intent":"weather","location_text":"NYC","current_location_text":"NYC","coordinates":null,"time_window":null,"activity":null,"location_source":"current"}'
    )])
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)

    assert handler._extract_weather_context("I'm in NYC now, will it rain?") == {
        "intent": "weather",
        "location_text": "NYC",
        "current_location_text": "NYC",
        "coordinates": None,
        "time_window": "now",
        "activity": "general",
        "location_source": "current",
    }


def test_history_grounding_accepts_all_caps_location_abbreviation() -> None:
    history = [handler.ContextInteraction("I'm in NYC now, will it rain?", "NYC conditions", "prior")]

    assert handler._history_location_is_grounded("NYC", history)


@pytest.mark.parametrize(
    "coordinates",
    [
        '{"latitude":"45.62","longitude":-78.42}',
        '{"latitude":true,"longitude":-78.42}',
        '{"latitude":45.62}',
        '{"latitude":45.62,"longitude":-78.42,"altitude":123}',
    ],
)
def test_interpretation_rejects_invalid_coordinate_schema_before_geocoding(monkeypatch: pytest.MonkeyPatch, coordinates: str) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response(
                '{"intent":"weather","location_text":null,"current_location_text":"",'
                f'"coordinates":{coordinates},"time_window":"today","activity":"general","location_source":"current"}}'
            )
        ]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)
    monkeypatch.setattr(handler, "_resolve_named_place", lambda *_args: pytest.fail("invalid coordinates must not geocode"))

    assert handler._reply_for_message("Weather at 45.62,-78.42") == handler.WEATHER_EXTRACTION_FALLBACK
    assert len(bedrock.calls) == 1


def test_conflicting_current_location_contract_is_rejected_before_geocoding(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Pine Ridge","current_location_text":"Toronto","coordinates":null,"time_window":"now","activity":"general","location_source":"history"}'),
        ]
    )
    configure(monkeypatch, bedrock)
    monkeypatch.setattr(handler, "_resolve_named_place", lambda *_args: pytest.fail("conflicting location must not geocode"))

    assert handler._reply_for_message("I'm in Toronto now. How are conditions?", [handler.ContextInteraction("Weather at Pine Ridge", "old", "a")]) == handler.WEATHER_EXTRACTION_FALLBACK


def test_null_current_location_text_is_malformed_before_geocoding(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Pine Ridge","current_location_text":null,"coordinates":null,"time_window":"now","activity":"general","location_source":"history"}'),
        ]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)
    monkeypatch.setattr(handler, "_resolve_named_place", lambda *_args: pytest.fail("malformed interpretation must not geocode"))

    assert handler._reply_for_message("I'm in Toronto now. How are conditions?", [handler.ContextInteraction("Weather at Pine Ridge", "old", "a")]) == handler.WEATHER_EXTRACTION_FALLBACK
    assert len(bedrock.calls) == 1


def test_history_selection_is_not_overridden_by_a_local_current_sms_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    """Natural-language precedence is enforced by the interpreter contract, not token matching."""
    history = [handler.ContextInteraction("Weather at Pine Ridge", "old", "a")]
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Pine Ridge","current_location_text":"","coordinates":null,"time_window":"now","activity":"general","location_source":"history"}'),
            model_response("Pine Ridge conditions are mild."),
        ]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)
    candidate = handler.LocationCandidate("Pine Ridge", 45.0, -78.0, "LAKE", "Ontario", "nrcan_geonames")
    resolved: list[str] = []
    monkeypatch.setattr(handler, "_resolve_named_place", lambda query: (resolved.append(query) or handler.LocationResolution(candidate, "resolved")))
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_coords: handler._normalize_hourly_weather(hourly_payload()))

    assert handler._reply_for_message("Toronto conditions now?", history) == "Pine Ridge conditions are mild."
    assert resolved == ["Pine Ridge"]


def test_named_place_without_a_location_source_is_rejected_before_geocoding(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Pine Ridge","current_location_text":"","coordinates":null,"time_window":"now","activity":"general","location_source":"none"}'),
        ]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)
    monkeypatch.setattr(handler, "_resolve_named_place", lambda *_args: pytest.fail("unsourced location must not geocode"))

    assert handler._reply_for_message("Toronto conditions now?") == handler.WEATHER_EXTRACTION_FALLBACK
    assert len(bedrock.calls) == 1


def test_location_free_follow_up_can_use_history_after_precedence_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    history = [handler.ContextInteraction("Weather at Pine Ridge", "old", "a")]
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Pine Ridge","current_location_text":"","coordinates":null,"time_window":"tomorrow","activity":"general","location_source":"history"}'),
            model_response("Pine Ridge conditions are mild."),
        ]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)
    candidate = handler.LocationCandidate("Pine Ridge", 45.0, -78.0, "LAKE", "Ontario", "nrcan_geonames")
    monkeypatch.setattr(handler, "_resolve_named_place", lambda _query: handler.LocationResolution(candidate, "resolved"))
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_coords: handler._normalize_hourly_weather(hourly_payload()))

    assert handler._reply_for_message("What about tomorrow?", history) == "Pine Ridge conditions are mild."


def test_history_source_must_match_the_newest_available_history_location(monkeypatch: pytest.MonkeyPatch) -> None:
    history = [handler.ContextInteraction("Weather at Pine Ridge", "old", "a")]
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Fake Lake","current_location_text":"","coordinates":null,"time_window":"tomorrow","activity":"general","location_source":"history"}'),
        ]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)
    monkeypatch.setattr(handler, "_resolve_named_place", lambda *_args: pytest.fail("unsourced history location must not geocode"))

    assert handler._reply_for_message("What about tomorrow?", history) == handler.WEATHER_EXTRACTION_FALLBACK
    assert len(bedrock.calls) == 1


def test_history_source_can_use_location_label_from_prior_assistant_output(monkeypatch: pytest.MonkeyPatch) -> None:
    history = [handler.ContextInteraction("What about tomorrow?", "Toronto conditions were mild.", "a")]
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Toronto","current_location_text":"","coordinates":null,"time_window":"tomorrow","activity":"general","location_source":"history"}'),
            model_response("Toronto conditions will be mild."),
        ]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)
    candidate = handler.LocationCandidate("Toronto", 43.65, -79.38, "CITY", "Ontario", "amazon_location_places")
    monkeypatch.setattr(handler, "_resolve_named_place", lambda _query: handler.LocationResolution(candidate, "resolved"))
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_coords: handler._normalize_hourly_weather(hourly_payload()))

    assert handler._reply_for_message("What about tomorrow?", history) == "Toronto conditions will be mild."


def test_stale_historical_place_in_advice_is_replaced_with_deterministic_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    history = [handler.ContextInteraction("Weather at Pine Ridge", "old", "a")]
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Toronto","current_location_text":"Toronto","coordinates":null,"time_window":"today","activity":"general","location_source":"current"}'),
            model_response("Pine Ridge will be mild today."),
        ]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)
    candidate = handler.LocationCandidate("Toronto", 43.65, -79.38, "CITY", "Ontario", "amazon_location_places")
    monkeypatch.setattr(handler, "_resolve_named_place", lambda _query: handler.LocationResolution(candidate, "resolved"))
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_coords: handler._normalize_hourly_weather(hourly_payload()))

    reply = handler._reply_for_message("Toronto conditions now?", history)

    assert "Pine Ridge" not in reply
    advice_payload = json.loads(json.loads(bedrock.calls[1]["messages"][0]["content"][0]["text"])["current_sms"])
    assert advice_payload["location"] == {"label": "Toronto", "coordinates": {"latitude": 43.65, "longitude": -79.38}}


def test_single_word_historical_place_in_advice_is_replaced_with_deterministic_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    history = [handler.ContextInteraction("Weather at Toronto", "old", "a")]
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Burnt Island Lake","current_location_text":"Burnt Island Lake","coordinates":null,"time_window":"today","activity":"general","location_source":"current"}'),
            model_response("Toronto will be mild today."),
        ]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)
    candidate = handler.LocationCandidate("Burnt Island Lake", 45.64, -78.62, "LAKE", "Ontario", "nrcan_geonames")
    monkeypatch.setattr(handler, "_resolve_named_place", lambda _query: handler.LocationResolution(candidate, "resolved"))
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_coords: handler._normalize_hourly_weather(hourly_payload()))

    reply = handler._reply_for_message("Burnt Island Lake conditions now?", history)

    assert "Toronto" not in reply


def test_historical_place_only_in_prior_assistant_output_is_filtered_from_advice(monkeypatch: pytest.MonkeyPatch) -> None:
    history = [handler.ContextInteraction("What about tomorrow?", "Toronto conditions were mild.", "a")]
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":"Burnt Island Lake","current_location_text":"Burnt Island Lake","coordinates":null,"time_window":"today","activity":"general","location_source":"current"}'),
            model_response("Toronto will be mild today."),
        ]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)
    candidate = handler.LocationCandidate("Burnt Island Lake", 45.64, -78.62, "LAKE", "Ontario", "nrcan_geonames")
    monkeypatch.setattr(handler, "_resolve_named_place", lambda _query: handler.LocationResolution(candidate, "resolved"))
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_coords: handler._normalize_hourly_weather(hourly_payload()))

    reply = handler._reply_for_message("Burnt Island Lake conditions now?", history)

    assert "Toronto" not in reply


def test_unclear_intent_makes_a_second_clarification_call(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"unclear","location_text":null,"current_location_text":"","coordinates":null,"time_window":"today","activity":"general","location_source":"none"}'),
            model_response("Could you clarify what you need?"),
        ]
    )
    sms = configure(monkeypatch, bedrock)

    handler.lambda_handler(sns_event("test-allowed-sender", "Can you help?"), None)

    assert len(bedrock.calls) == 2
    assert bedrock.calls[1]["system"][0]["text"] == handler.CLARIFICATION_SYSTEM_PROMPT
    assert sms.calls[0]["MessageBody"] == "Could you clarify what you need?"


def test_out_of_range_current_coordinates_request_correction_after_weather_intent(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":null,"current_location_text":"","coordinates":null,"time_window":"today","activity":"general","location_source":"current"}'),
            model_response(handler.WEATHER_COORDINATE_FALLBACK),
        ]
    )
    sms = configure(monkeypatch, bedrock)
    history = [handler.ContextInteraction("Weather at Toronto", "Toronto: rain tonight.", "prior")]
    monkeypatch.setattr(handler, "_load_context", lambda _phone: (history, True))

    handler.lambda_handler(sns_event("test-allowed-sender", "Check 91,-78.42 for me"), None)

    assert len(bedrock.calls) == 2
    assert bedrock.calls[1]["system"][0]["text"] == handler.COORDINATE_CORRECTION_SYSTEM_PROMPT
    assert sms.calls[0]["MessageBody"] == handler.WEATHER_COORDINATE_FALLBACK
    fallback = json.loads(bedrock.calls[1]["messages"][0]["content"][0]["text"])
    assert fallback["current_sms"] == "Check 91,-78.42 for me"
    assert fallback["history"] == [{"input": "Weather at Toronto", "output": "Toronto: rain tonight."}]


def test_history_coordinates_are_not_inherited_for_a_follow_up(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response(
                '{"intent":"weather","location_text":null,"current_location_text":"",'
                '"coordinates":{"latitude":45.62,"longitude":-78.42},"time_window":"tomorrow",'
                '"activity":"general","location_source":"history"}'
            ),
            model_response(handler.WEATHER_COORDINATE_FALLBACK),
        ]
    )
    configure(monkeypatch, bedrock)
    history = [handler.ContextInteraction("Weather at 45.62,-78.42", "Rain yesterday.", "prior")]

    assert handler._reply_for_message("What about tomorrow?", history) == handler.WEATHER_COORDINATE_FALLBACK
    assert len(bedrock.calls) == 2
    fallback = json.loads(bedrock.calls[1]["messages"][0]["content"][0]["text"])
    assert fallback["current_sms"] == "What about tomorrow?"
    assert fallback["history"] == [{"input": "Weather at 45.62,-78.42", "output": "Rain yesterday."}]


def test_interpretation_envelope_repeats_current_toronto_after_pine_history() -> None:
    history = [handler.ContextInteraction("Weather at Pine Ridge", "old weather", "a")]

    payload = json.loads(handler._interpretation_bedrock_context("I'm in Toronto now... what's the weather?", history))

    assert payload["current_sms"] == "I'm in Toronto now... what's the weather?"
    assert payload["history"][0]["input"] == "Weather at Pine Ridge"
    assert payload["authoritative_current_sms"] == "I'm in Toronto now... what's the weather?"


def test_follow_up_uses_location_selected_from_history_by_interpreter(monkeypatch: pytest.MonkeyPatch) -> None:
    history = [handler.ContextInteraction("Weather at Old Lake", "old", "a"), handler.ContextInteraction("I'm now at New Lake", "new", "b")]
    captured: list[str] = []
    candidate = handler.LocationCandidate("New Lake", 45.0, -78.0, "LAKE", "Ontario", "nrcan_geonames")
    monkeypatch.setattr(
        handler,
        "_extract_weather_context",
        lambda *_args: {"intent": "weather", "location_text": "New Lake", "coordinates": None, "time_window": "tomorrow", "activity": "general", "location_source": "history"},
    )
    monkeypatch.setattr(handler, "_resolve_named_place", lambda query: (captured.append(query) or handler.LocationResolution(candidate, "resolved")))
    monkeypatch.setattr(handler, "_weather_reply", lambda *_args: "ok")

    assert handler._reply_for_message("What about tomorrow?", history) == "ok"
    assert captured == ["New Lake"]


def test_named_location_does_not_accept_invented_model_coordinates(monkeypatch: pytest.MonkeyPatch) -> None:
    context = {"intent": "weather", "location_text": "Toronto", "coordinates": {"latitude": 0, "longitude": 0}, "time_window": "today", "activity": "general", "location_source": "current"}
    candidate = handler.LocationCandidate("Toronto", 43.65, -79.38, "CITY", "Ontario", "amazon_location_places")
    monkeypatch.setattr(handler, "_extract_weather_context", lambda *_args: context)
    monkeypatch.setattr(handler, "_resolve_named_place", lambda _query: handler.LocationResolution(candidate, "resolved"))
    captured: list[tuple[float, float]] = []
    monkeypatch.setattr(handler, "_weather_reply", lambda _text, coordinates, *_args: (captured.append(coordinates) or "ok"))

    assert handler._reply_for_message("Toronto weather") == "ok"
    assert captured == [(43.65, -79.38)]


def test_model_coordinate_conflict_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        handler,
        "_extract_weather_context",
        lambda *_args: {"intent": "weather", "location_text": "", "coordinates": {"latitude": 0, "longitude": 0}, "time_window": "today", "activity": "general", "location_source": "current"},
    )
    monkeypatch.setattr(handler, "_weather_reply", lambda *_args: pytest.fail("weather must not run"))

    assert handler._reply_for_message("weather at 45.62,-78.42") == handler.WEATHER_COORDINATE_FALLBACK


def test_weather_provider_failure_uses_fixed_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":null,"current_location_text":"","coordinates":{"latitude":45.62,"longitude":-78.42},"time_window":"today","activity":"camping","location_source":"current"}'),
            model_response(handler.WEATHER_PROVIDER_FALLBACK),
        ]
    )
    sms = configure(monkeypatch, bedrock)
    history = [handler.ContextInteraction("Weather at Toronto", "Toronto: rain tonight.", "prior")]
    monkeypatch.setattr(handler, "_load_context", lambda _phone: (history, True))

    def failed_urlopen(_url: str, *, timeout: int) -> FakeWeatherResponse:
        raise OSError("provider unavailable")

    monkeypatch.setattr(handler, "urlopen", failed_urlopen)
    handler.lambda_handler(sns_event("test-allowed-sender", "Weather at 45.62,-78.42"), None)

    assert sms.calls[0]["MessageBody"] == handler.WEATHER_PROVIDER_FALLBACK
    assert len(bedrock.calls) == 2
    assert bedrock.calls[1]["system"][0]["text"] == handler.WEATHER_UNAVAILABLE_SYSTEM_PROMPT
    fallback = json.loads(bedrock.calls[1]["messages"][0]["content"][0]["text"])
    assert fallback["current_sms"] == "Weather at 45.62,-78.42"
    assert fallback["history"] == [{"input": "Weather at Toronto", "output": "Toronto: rain tonight."}]


def test_weather_extraction_failure_uses_fixed_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bedrock = FakeBedrockClient(error=RuntimeError("model unavailable"))
    sms = configure(monkeypatch, bedrock)
    provider_calls = 0

    def fake_urlopen(_url: str, *, timeout: int) -> FakeWeatherResponse:
        nonlocal provider_calls
        provider_calls += 1
        return FakeWeatherResponse(hourly_payload())

    monkeypatch.setattr(handler, "urlopen", fake_urlopen)
    handler.lambda_handler(sns_event("test-allowed-sender", "Weather at 45.62,-78.42"), None)

    assert sms.calls[0]["MessageBody"] == handler.WEATHER_EXTRACTION_FALLBACK
    assert provider_calls == 0


def test_fenced_weather_extraction_json_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response(
                    "```json\n{\"intent\":\"weather\",\"location_text\":null,\"current_location_text\":\"\",\"coordinates\":{\"latitude\":45.62,\"longitude\":-78.42},\"time_window\":\"tonight\",\"activity\":\"canoeing\",\"location_source\":\"current\"}\n```"
            ),
            model_response("Set the tarp before rain and avoid open-water crossings."),
        ]
    )
    sms = configure(monkeypatch, bedrock)
    monkeypatch.setattr(handler, "urlopen", lambda _url, *, timeout: FakeWeatherResponse(hourly_payload()))

    handler.lambda_handler(sns_event("test-allowed-sender", "Canoe at 45.62,-78.42"), None)

    assert len(bedrock.calls) == 2
    assert "tarp" in sms.calls[0]["MessageBody"].lower()


def test_malformed_weather_extraction_uses_safe_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response("Intent: weather; canoe tonight."),
        ]
    )
    sms = configure(monkeypatch, bedrock)
    monkeypatch.setattr(handler, "urlopen", lambda _url, *, timeout: FakeWeatherResponse(hourly_payload()))

    handler.lambda_handler(sns_event("test-allowed-sender", "Weather at 45.62,-78.42"), None)

    assert len(bedrock.calls) == 1
    assert sms.calls[0]["MessageBody"] == handler.WEATHER_EXTRACTION_FALLBACK


def test_advice_failure_uses_deterministic_weather_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bedrock = FakeBedrockClient(
        responses=[
            model_response('{"intent":"weather","location_text":null,"current_location_text":"","coordinates":{"latitude":45.62,"longitude":-78.42},"time_window":"tonight","activity":"canoeing","location_source":"current"}'),
        ],
    )
    sms = configure(monkeypatch, bedrock)
    monkeypatch.setattr(handler, "urlopen", lambda _url, *, timeout: FakeWeatherResponse(hourly_payload()))
    original = handler._bedrock_converse
    calls = 0

    def fail_second_call(**kwargs: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("advice unavailable")
        return original(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(handler, "_bedrock_converse", fail_second_call)
    handler.lambda_handler(sns_event("test-allowed-sender", "Canoe at 45.62,-78.42 tonight"), None)

    assert "gusts 42 km/h" in sms.calls[0]["MessageBody"]
    assert "Avoid open-water canoeing" in sms.calls[0]["MessageBody"]
    assert "2026-08-30" not in sms.calls[0]["MessageBody"]
    assert "T00:00" not in sms.calls[0]["MessageBody"]


def test_deterministic_weather_summary_omits_internal_forecast_timestamp() -> None:
    summary = handler._deterministic_weather_summary(
        {"time": "2026-08-30T00:00", "temperature_c": 18, "precipitation_probability": 1, "gust_kmh": 9},
        ["Keep normal caution."],
    )

    assert summary == "18C, rain 1%, gusts 9 km/h. Keep normal caution."
    assert "2026-08-30" not in summary


def test_sms_bound_normalizes_unicode_and_counts_gsm_extensions() -> None:
    output = handler._bound_sms("“Hello” — " + "^" * 100, handler.FALLBACK_REPLY)

    assert "“" not in output
    assert "—" not in output
    assert len(output) < 160
    assert sum(2 if char in handler.GSM_EXTENDED else 1 for char in output) <= 160


def test_sms_bound_formats_degree_symbols_as_readable_gsm_text() -> None:
    assert handler._bound_sms("15°C, 70°F", handler.FALLBACK_REPLY) == "15 C, 70 F"


def test_context_is_ordered_filtered_and_user_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 2_000_000_000
    monkeypatch.setattr(handler.time, "time", lambda: now)
    dynamo = FakeDynamoClient(items=[
        {"user_phone_e164": {"S": "+15550000001"}, "created_at": {"S": "2026-08-29T10:00:00Z#a"}, "input_body": {"S": "first"}, "output_body": {"S": "one"}, "ttl": {"N": str(now + 10)}},
        {"user_phone_e164": {"S": "+15550000001"}, "created_at": {"S": "2026-08-29T11:00:00Z#b"}, "input_body": {"S": "second"}, "output_body": {"S": "two"}, "ttl": {"N": str(now + 10)}},
        {"user_phone_e164": {"S": "+15550000002"}, "created_at": {"S": "2026-08-29T12:00:00Z#c"}, "input_body": {"S": "other user"}, "output_body": {"S": "no"}, "ttl": {"N": str(now + 10)}},
        {"user_phone_e164": {"S": "+15550000001"}, "created_at": {"S": "2026-08-20T12:00:00Z#d"}, "input_body": {"S": "expired"}, "output_body": {"S": "no"}, "ttl": {"N": str(now - 1)}},
    ])
    monkeypatch.setenv("MESSAGE_CONTEXT_TABLE", "context")
    monkeypatch.setattr(handler.boto3, "client", lambda service: dynamo)

    history, readable = handler._load_context("+15550000001")

    assert readable is True
    assert [item.input_body for item in history] == ["first", "second"]
    assert dynamo.queries[0]["ExpressionAttributeNames"] == {"#ttl": "ttl"}
    assert dynamo.queries[0]["FilterExpression"] == "#ttl > :now AND attribute_exists(output_body)"


def test_context_query_paginates_past_filtered_rows_to_fill_history_window(monkeypatch: pytest.MonkeyPatch) -> None:
    valid_items = [
        {
            "user_phone_e164": {"S": "+15550000001"},
            "created_at": {"S": f"2026-08-30T04:0{i}:00Z#valid-{i}"},
            "input_body": {"S": f"Weather at Lake {i}"},
            "output_body": {"S": f"Lake {i} forecast"},
            "ttl": {"N": "2000000000"},
        }
        for i in range(5)
    ]
    dynamo = PaginatedDynamoClient([
        {"Items": [], "LastEvaluatedKey": {"user_phone_e164": {"S": "+15550000001"}, "created_at": {"S": "filtered"}}},
        {"Items": valid_items},
    ])
    monkeypatch.setenv("MESSAGE_CONTEXT_TABLE", "context")
    monkeypatch.setattr(handler.context_store.time, "time", lambda: 1_000_000_000)
    monkeypatch.setattr(handler.boto3, "client", lambda _service: dynamo)

    history, readable = handler._load_context("+15550000001")

    assert readable is True
    assert len(history) == handler.CONTEXT_HISTORY_LIMIT
    assert len(dynamo.queries) == 2
    assert dynamo.queries[1]["ExclusiveStartKey"] == {"user_phone_e164": {"S": "+15550000001"}, "created_at": {"S": "filtered"}}


def test_realistic_context_history_reaches_interpretation_and_synthesis_for_follow_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior_input = "I'm in Toronto now... what's the weather?"
    prior_output = "Toronto: 8 C with rain; use caution on exposed trails."
    dynamo = FakeDynamoClient(items=[
        {
            "user_phone_e164": {"S": "+15550000001"},
            "created_at": {"S": "2026-08-30T04:04:42.000Z#prior"},
            "message_id": {"S": "prior"},
            "input_body": {"S": prior_input},
            "output_body": {"S": prior_output},
            "ttl": {"N": str(2_000_000_000)},
        }
    ])
    bedrock = FakeBedrockClient(responses=[
        model_response(
            '{"intent":"weather","location_text":"Toronto","current_location_text":"",'
            '"coordinates":null,"time_window":"tomorrow","activity":"general","location_source":"history"}'
        ),
        model_response("Toronto tomorrow: check rain and wind before heading out."),
    ])
    configure(monkeypatch, bedrock, dynamo)
    monkeypatch.setenv("MESSAGE_CONTEXT_TABLE", "context")
    monkeypatch.setenv("ALLOWED_PHONE_NUMBER", "+15550000001")
    monkeypatch.setattr(handler.time, "time", lambda: 1_000_000_000)
    monkeypatch.setattr(handler.context_store.time, "time", lambda: 1_000_000_000)
    candidate = handler.LocationCandidate("Toronto", 43.65, -79.38, "CITY", "Ontario", "amazon_location_places")
    monkeypatch.setattr(handler, "_resolve_named_place", lambda _query: handler.LocationResolution(candidate, "resolved"))
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_coords: handler._normalize_hourly_weather(hourly_payload()))

    assert handler.lambda_handler(sns_event("+15550000001", "What about tomorrow?", "follow-up"), None) == {"status": "replied"}
    assert len(bedrock.calls) == 2

    interpretation = json.loads(bedrock.calls[0]["messages"][0]["content"][0]["text"])
    assert interpretation["current_sms"] == "What about tomorrow?"
    assert interpretation["history"] == [{"input": prior_input, "output": prior_output}]
    assert "input is the user's SMS and output is the assistant's SMS" in interpretation["instruction"]

    synthesis = json.loads(bedrock.calls[1]["messages"][0]["content"][0]["text"])
    assert synthesis["history"] == interpretation["history"]
    synthesis_input = json.loads(synthesis["current_sms"])
    assert synthesis_input["inbound_sms"] == "What about tomorrow?"
    assert synthesis_input["location"]["label"] == "Toronto"


def test_bedrock_context_labels_current_and_history() -> None:
    payload = json.loads(handler._bedrock_context("What about tomorrow?", [handler.ContextInteraction("Weather at 45.62,-78.42", "Rain", "a")]))

    assert payload["current_sms"] == "What about tomorrow?"
    assert payload["history"] == [{"input": "Weather at 45.62,-78.42", "output": "Rain"}]
    assert "CURRENT SMS" in payload["instruction"]
    assert "Do not claim you cannot remember" in payload["instruction"]


def test_duplicate_sns_delivery_stops_before_second_bedrock_call(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock, dynamo = FakeBedrockClient(), FakeDynamoClient()
    monkeypatch.setenv("MESSAGE_CONTEXT_TABLE", "context")
    configure(monkeypatch, bedrock, dynamo)
    event = sns_event("test-allowed-sender", "hello", "same-id")

    assert handler.lambda_handler(event, None)["status"] == "replied"
    assert handler.lambda_handler(event, None) == {"status": "ignored", "reason": "duplicate_delivery"}
    assert len(bedrock.calls) == 2


def test_context_write_failure_stops_before_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock, dynamo = FakeBedrockClient(), FakeDynamoClient(fail_put=True)
    monkeypatch.setenv("MESSAGE_CONTEXT_TABLE", "context")
    sms = configure(monkeypatch, bedrock, dynamo)

    assert handler.lambda_handler(sns_event("test-allowed-sender", "hello"), None) == {"status": "failed", "reason": "storage_unavailable"}
    assert sms.calls == []


def test_context_read_failure_keeps_general_reply_without_history(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock, dynamo = FakeBedrockClient(), FakeDynamoClient(fail_query=True)
    monkeypatch.setenv("MESSAGE_CONTEXT_TABLE", "context")
    configure(monkeypatch, bedrock, dynamo)

    assert handler.lambda_handler(sns_event("test-allowed-sender", "hello"), None)["status"] == "replied"
    payload = json.loads(bedrock.calls[0]["messages"][0]["content"][0]["text"])
    assert payload["history"] == []


def test_interpreter_rejects_extra_schema_key_before_geocoding(monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock = FakeBedrockClient(
        responses=[model_response('{"intent":"weather","location_text":"New Lake","current_location_text":"New Lake","coordinates":null,"time_window":"today","activity":"general","location_source":"current","ignored":"value"}')]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda _service: bedrock)
    monkeypatch.setattr(handler, "_resolve_named_place", lambda *_args: pytest.fail("extra schema field must not geocode"))
    history = [handler.ContextInteraction("Weather at Old Lake", "old", "a")]

    assert handler._reply_for_message("Weather in New Lake", history) == handler.WEATHER_EXTRACTION_FALLBACK

    payload = json.loads(bedrock.calls[0]["messages"][0]["content"][0]["text"])
    assert payload["current_sms"] == "Weather in New Lake"
    assert payload["history"] == [{"input": "Weather at Old Lake", "output": "old"}]
    assert payload["authoritative_current_sms"] == "Weather in New Lake"
    assert payload["instruction"].startswith("AUTHORITATIVE CURRENT SMS")
    assert len(bedrock.calls) == 1
