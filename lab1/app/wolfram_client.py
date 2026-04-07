import logging
import time

import requests


class WolframClient:
    def __init__(
        self,
        appid: str,
        base_url: str,
        timeout_seconds: int,
        max_retries: int,
        logger: logging.Logger,
    ) -> None:
        self._appid = appid
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._logger = logger

    def ask(self, query: str) -> dict:
        # Формируем параметры HTTP GET-запроса к Wolfram Alpha API.
        params = {
            "appid": self._appid,
            "input": query,
            "output": "json",
            "format": "plaintext",
        }

        self._logger.info("Requesting API for query: %s", query)

        # Делаем несколько попыток при временных сетевых сбоях.
        attempts_total = self._max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts_total + 1):
            try:
                response = requests.get(self._base_url, params=params, timeout=self._timeout_seconds)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                if attempt < attempts_total:
                    self._logger.warning(
                        "Attempt %s/%s failed for query '%s': %s. Retrying...",
                        attempt,
                        attempts_total,
                        query,
                        exc,
                    )
                    # Небольшая пауза перед следующей попыткой.
                    time.sleep(min(attempt, 3))
                    continue
            except ValueError as exc:
                raise RuntimeError(f"Failed to decode JSON for query '{query}': {exc}") from exc

        raise RuntimeError(f"Network/API request failed for query '{query}': {last_error}") from last_error
