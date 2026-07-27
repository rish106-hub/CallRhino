import json

import httpx

from callrhino.config import Settings
from callrhino.services.sarvam import SarvamChatClient


def test_sends_documented_structured_output_contract(valid_brief_data: dict) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_test",
                "model": "sarvam-105b",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(valid_brief_data),
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            },
        )

    settings = Settings(SARVAM_API_KEY="test_key", _env_file=None)
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    client = SarvamChatClient(settings, client=http_client)

    result = client.generate_structured(
        messages=[{"role": "user", "content": "test"}],
        schema_name="meeting_brief",
        schema={"type": "object", "properties": {}, "additionalProperties": False},
    )

    body = captured["body"]
    assert captured["headers"]["api-subscription-key"] == "test_key"
    assert body["model"] == "sarvam-105b"
    assert body["temperature"] == 0
    assert body["reasoning_effort"] is None
    assert body["max_tokens"] == 4096
    assert body["n"] == 1
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert result.usage.total_tokens == 150
    assert result.data["summary"]["topics"] == ["release", "onboarding"]
