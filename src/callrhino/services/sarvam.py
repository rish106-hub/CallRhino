import json
from dataclasses import dataclass
from typing import Any

import httpx

from callrhino.config import Settings


class SarvamError(RuntimeError):
    """Base error for Sarvam API failures."""


class SarvamConfigurationError(SarvamError):
    """Raised when required credentials are missing."""


class SarvamResponseError(SarvamError):
    """Raised when Sarvam returns an unusable response."""

    def __init__(self, message: str, usage: "TokenUsage | None" = None) -> None:
        super().__init__(message)
        self.usage = usage or TokenUsage()


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class StructuredChatResult:
    content: str
    data: dict[str, Any]
    usage: TokenUsage
    model: str
    request_id: str | None


class SarvamChatClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.sarvam_api_key:
            raise SarvamConfigurationError(
                "SARVAM_API_KEY is missing. Add it to .env before processing a meeting."
            )
        self._settings = settings
        self._client = client or httpx.Client(timeout=settings.sarvam_timeout_seconds)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "SarvamChatClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def generate_structured(
        self,
        *,
        messages: list[dict[str, str]],
        schema_name: str,
        schema: dict[str, Any],
    ) -> StructuredChatResult:
        payload = {
            "model": self._settings.sarvam_chat_model,
            "messages": messages,
            "temperature": 0,
            "reasoning_effort": None,
            "max_tokens": 4096,
            "n": 1,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        }

        try:
            response = self._client.post(
                self._settings.sarvam_chat_url,
                headers={
                    "api-subscription-key": self._settings.sarvam_api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise SarvamError("Sarvam timed out. Retry the meeting once.") from exc
        except httpx.HTTPStatusError as exc:
            detail = _extract_error_detail(exc.response)
            raise SarvamError(
                f"Sarvam returned HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SarvamError("Could not reach Sarvam. Check the network and retry.") from exc

        body = response.json()
        raw_usage = body.get("usage") or {}
        usage = TokenUsage(
            prompt_tokens=int(raw_usage.get("prompt_tokens") or 0),
            completion_tokens=int(raw_usage.get("completion_tokens") or 0),
            total_tokens=int(raw_usage.get("total_tokens") or 0),
        )
        try:
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise KeyError("empty message content")
            data = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            finish_reason = _finish_reason(body)
            raise SarvamResponseError(
                f"Sarvam returned an invalid structured response "
                f"(finish_reason={finish_reason}).",
                usage=usage,
            ) from exc
        return StructuredChatResult(
            content=content,
            data=data,
            usage=usage,
            model=str(body.get("model") or self._settings.sarvam_chat_model),
            request_id=body.get("id"),
        )


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300] or "Unknown provider error"

    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)[:300]
        return str(body.get("message") or body.get("detail") or body)[:300]
    return str(body)[:300]


def _finish_reason(body: dict[str, Any]) -> str:
    try:
        return str(body["choices"][0].get("finish_reason") or "unknown")
    except (KeyError, IndexError, TypeError):
        return "unknown"
