"""Provider clients parse responses and count tokens (mock transports); recordings replay."""

from __future__ import annotations

import json

import httpx
import pytest

from research_engine.agents.output import parse_output, wire_schema
from research_engine.agents.prompts import PROMPT_VERSION, platform_block
from research_engine.agents.providers import (
    AnthropicProvider,
    OpenAICompatibleProvider,
    ProviderConfigurationError,
    ProviderError,
    ProviderRefusal,
    RecordedResponseProvider,
    RecordingMissing,
    RecordingProvider,
    ReferenceHeuristicProvider,
    build_provider,
)
from research_engine.agents.providers.base import ChatMessage, ModelRequest, RequestMetadata


def _request(text="hello", purpose="synthesis", schema=True):
    return ModelRequest(
        system="system prompt",
        messages=(ChatMessage("user", text),),
        metadata=RequestMetadata("dec-1", "single", purpose, PROMPT_VERSION),
        json_schema=wire_schema(["final"]) if schema else None,
        max_output_tokens=512,
    )


def test_anthropic_provider_builds_messages_request_and_counts_tokens():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "model": "claude-sonnet-5-5",
                "stop_reason": "end_turn",
                "content": [
                    {"type": "thinking", "thinking": ""},
                    {"type": "text", "text": '{"action":"final"}'},
                ],
                "usage": {"input_tokens": 100, "cache_read_input_tokens": 20, "output_tokens": 30},
            },
        )

    provider = AnthropicProvider(api_key="test-key", transport=httpx.MockTransport(handler))
    response = provider.generate(_request())
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "test-key"
    assert seen["headers"]["anthropic-version"] == "2026-10-21"
    body = seen["body"]
    assert body["model"] == "claude-sonnet-5-5" and body["max_tokens"] == 512
    assert body["system"] == "system prompt"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in body and "thinking" not in body
    assert response.text == '{"action":"final"}'  # thinking blocks are never read
    assert (response.input_tokens, response.output_tokens) == (120, 30)
    assert (response.provider, response.model, response.response_id) == (
        "anthropic",
        "claude-sonnet-5-5",
        "msg_1",
    )


@pytest.mark.parametrize(
    "status,transient", [(429, True), (529, True), (500, True), (400, False), (401, False)]
)
def test_anthropic_errors_are_typed(status, transient):
    transport = httpx.MockTransport(
        lambda r: httpx.Response(status, json={"error": {"type": "x", "message": "boom"}})
    )
    provider = AnthropicProvider(api_key="k", transport=transport)
    with pytest.raises(ProviderError) as info:
        provider.generate(_request())
    assert info.value.transient is transient and info.value.status == status


def test_anthropic_refusal_and_missing_key(monkeypatch):
    transport = httpx.MockTransport(
        lambda r: httpx.Response(
            200,
            json={"stop_reason": "refusal", "stop_details": {"category": "cyber"}, "content": []},
        )
    )
    with pytest.raises(ProviderRefusal):
        AnthropicProvider(api_key="k", transport=transport).generate(_request())
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderConfigurationError):
        AnthropicProvider().generate(_request())


def test_openai_compatible_standard_and_usage():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "cmpl-1",
                "model": "llama-3.3-70b-versatile",
                "choices": [
                    {"message": {"content": '{"action":"final"}'}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 77, "completion_tokens": 11},
            },
        )

    provider = OpenAICompatibleProvider(
        "llama-3.3-70b-versatile",
        base_url="https://api.groq.com/openai/v1",
        api_key="gk",
        provider_label="groq",
        seed=7,
        transport=httpx.MockTransport(handler),
    )
    response = provider.generate(_request())
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["auth"] == "Bearer gk"
    body = seen["body"]
    assert body["messages"][0] == {"role": "system", "content": "system prompt"}
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["seed"] == 7
    assert (response.input_tokens, response.output_tokens, response.provider) == (77, 11, "groq")


def test_openai_compatible_azure_deployment_and_local_server():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 1}},
        )

    azure = OpenAICompatibleProvider(
        "gpt-x",
        base_url="https://res.openai.azure.com",
        api_key="az",
        azure_deployment="fi-agents",
        azure_api_version="2025-01-01",
        transport=httpx.MockTransport(handler),
    )
    azure.generate(_request())
    assert seen["url"].startswith("https://res.openai.azure.com/openai/deployments/fi-agents/")
    assert "api-version=2025-01-01" in seen["url"]
    assert seen["headers"]["api-key"] == "az" and "authorization" not in seen["headers"]
    local = OpenAICompatibleProvider(
        "qwen-local",
        base_url="http://localhost:11434/v1",
        api_key_required=False,
        priced=False,
        response_format="json_object",
        transport=httpx.MockTransport(handler),
    )
    local.generate(_request())
    assert "authorization" not in seen["headers"]


def test_recording_roundtrip_and_explicit_missing(tmp_path):
    recorder = RecordingProvider(ReferenceHeuristicProvider(), tmp_path / "rec")
    request = _request(platform_block("turn", {"role": "single", "allowedActions": ["final"]}))
    live = recorder.generate(request)
    assert live.recorded_response_id and live.recorded_response_id.startswith("rec-")
    replay = RecordedResponseProvider(tmp_path / "rec")
    assert (replay.provider, replay.model) == ("reference", "reference-heuristic-v1")
    again = replay.generate(request)
    assert (again.text, again.input_tokens, again.recorded_response_id) == (
        live.text,
        live.input_tokens,
        live.recorded_response_id,
    )
    changed = _request(request.messages[0].content + " ")
    with pytest.raises(RecordingMissing):
        replay.generate(changed)
    # A second identical request needs its own recording (occurrence index).
    with pytest.raises(RecordingMissing):
        replay.generate(request)
    manifest = json.loads((tmp_path / "rec" / "manifest.json").read_text())
    assert manifest["requestTextsStored"] is False and "not a hosted LLM" in manifest["disclosure"]


def test_reference_provider_is_labelled_and_schema_valid():
    provider = build_provider("reference")
    assert (provider.provider, provider.model, provider.priced) == (
        "reference",
        "reference-heuristic-v1",
        False,
    )
    text = (
        platform_block("context", {"retrievalMode": "none"})
        + "\n\n"
        + platform_block(
            "turn", {"role": "single", "allowedActions": ["final"], "allowedTools": []}
        )
    )
    response = provider.generate(_request(text))
    parsed = parse_output(response.text, ["final"])
    assert parsed.status == "insufficient_evidence" and parsed.decision == "abstain"
    assert response.input_tokens > 0 and response.output_tokens > 0


def test_build_provider_requires_explicit_configuration():
    with pytest.raises(ProviderConfigurationError):
        build_provider("recorded")
    with pytest.raises(ProviderConfigurationError):
        build_provider("openai")
    with pytest.raises(ProviderConfigurationError):
        build_provider("nonexistent")


def test_refusals_carry_the_reported_usage():
    anthropic = httpx.MockTransport(
        lambda r: httpx.Response(
            200,
            json={
                "stop_reason": "refusal",
                "stop_details": {"category": "cyber"},
                "content": [],
                "model": "claude-sonnet-5-5",
                "usage": {
                    "input_tokens": 900,
                    "cache_read_input_tokens": 100,
                    "output_tokens": 12,
                },
            },
        )
    )
    with pytest.raises(ProviderRefusal) as info:
        AnthropicProvider(api_key="k", transport=anthropic).generate(_request())
    assert (info.value.input_tokens, info.value.output_tokens) == (1000, 12)
    assert info.value.reported_usage

    no_usage = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"stop_reason": "refusal", "content": []})
    )
    with pytest.raises(ProviderRefusal) as info:
        AnthropicProvider(api_key="k", transport=no_usage).generate(_request())
    assert not info.value.reported_usage

    openai = httpx.MockTransport(
        lambda r: httpx.Response(
            200,
            json={
                "model": "gpt-test",
                "choices": [{"message": {"content": None, "refusal": "no"}}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 3},
            },
        )
    )
    provider = OpenAICompatibleProvider(
        "gpt-test", base_url="https://example.test/v1", api_key="k", transport=openai
    )
    with pytest.raises(ProviderRefusal) as info:
        provider.generate(_request())
    assert (info.value.input_tokens, info.value.output_tokens) == (40, 3)
