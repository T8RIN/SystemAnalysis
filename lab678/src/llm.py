from __future__ import annotations

from typing import Any

import requests


class LocalLLMClient:
    def __init__(
        self,
        base_url: str,
        model: str | None,
        timeout: int,
        max_tokens: int,
        temperature: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature

    def list_models(self) -> list[str]:
        try:
            response = requests.get(f"{self.base_url}/models", timeout=5)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException:
            return []
        models = data.get("data", [])
        return [str(item.get("id")) for item in models if item.get("id")]

    def is_available(self) -> bool:
        return bool(self.list_models())

    def complete(self, prompt: str) -> str:
        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        model = self.model or self._first_model()
        if model:
            payload["model"] = model

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"]).strip()
        except requests.RequestException as exc:
            raise RuntimeError(f"сервер LLM недоступен: {exc}") from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("сервер LLM вернул неожиданный формат ответа") from exc

    def _first_model(self) -> str | None:
        models = self.list_models()
        return models[0] if models else None
