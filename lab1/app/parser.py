from typing import Any


PREFERRED_TITLES = (
    "Result",
    "Exact result",
    "Decimal approximation",
    "Distance",
    "Current result",
    "Definitions",
    "Translation",
)


def _extract_pods(query_result: dict[str, Any]) -> list[dict[str, Any]]:
    # Извлекаем все pod-блоки с непустым plaintext.
    pods = query_result.get("pods", []) or []
    result: list[dict[str, Any]] = []

    for pod in pods:
        title = str(pod.get("title", "Untitled")).strip() or "Untitled"
        subpods = pod.get("subpods", [])
        if isinstance(subpods, dict):
            subpods = [subpods]

        texts: list[str] = []
        for subpod in subpods:
            text = str(subpod.get("plaintext", "")).strip()
            if text:
                texts.append(text)

        if texts:
            result.append({"title": title, "plaintext": texts})

    return result


def _pick_summary(parsed_pods: list[dict[str, Any]]) -> str:
    if not parsed_pods:
        return "No plaintext result found"

    # Сначала пытаемся взять ответ из приоритетных pod-ов.
    for preferred in PREFERRED_TITLES:
        for pod in parsed_pods:
            if pod["title"].lower() == preferred.lower():
                return pod["plaintext"][0]

    # Затем ищем любой pod, в названии которого есть "result".
    for pod in parsed_pods:
        if "result" in pod["title"].lower():
            return pod["plaintext"][0]

    # Если ничего не подошло, возвращаем первый доступный plaintext.
    return parsed_pods[0]["plaintext"][0]


def extract_key_data(api_response: dict[str, Any]) -> dict[str, Any]:
    # Формируем компактную структуру с ключевыми данными для отчета.
    query_result = api_response.get("queryresult", {})
    parsed_pods = _extract_pods(query_result)

    return {
        "success": bool(query_result.get("success", False)),
        "error": query_result.get("error"),
        "numpods": query_result.get("numpods", 0),
        "summary": _pick_summary(parsed_pods),
        "pods": parsed_pods,
    }
