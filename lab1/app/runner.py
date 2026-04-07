import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .parser import extract_key_data
from .queries import QueryTask
from .wolfram_client import WolframClient


@dataclass(frozen=True)
class RunArtifacts:
    extracted_file: Path
    report_file: Path
    raw_dir: Path


def _slugify(value: str) -> str:
    # Готовим безопасную часть имени файла из текста запроса.
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")[:80] or "query"


def _save_json(path: Path, data: dict) -> None:
    # Сохраняем JSON в UTF-8 с отступами для удобного просмотра.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _save_report(path: Path, results: list[dict]) -> None:
    # Собираем человекочитаемый текстовый отчет.
    lines: list[str] = []
    lines.append(f"Wolfram Alpha Lab Report")
    lines.append(f"Generated at: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    for item in results:
        lines.append(f"[{item['id']:02d}] {item['title']}")
        lines.append(f"Query: {item['query']}")
        lines.append(f"Status: {item['status']}")

        if item["status"] == "ok":
            lines.append(f"Summary: {item['parsed']['summary']}")
            lines.append(f"Raw file: {item['raw_file']}")
        else:
            lines.append(f"Error: {item['error']}")

        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_queries(
        client: WolframClient,
        tasks: list[QueryTask],
        output_dir: Path,
        logger: logging.Logger,
) -> RunArtifacts:
    # Создаем папки для итоговых файлов и "сырых" ответов API.
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw_responses"
    raw_dir.mkdir(parents=True, exist_ok=True)

    extracted_results: list[dict] = []

    for task in tasks:
        logger.info("Executing query %s/%s: %s", task.id, len(tasks), task.query)

        # Базовая структура результата по одному запросу.
        result_item = {
            "id": task.id,
            "title": task.title,
            "query": task.query,
            "required": task.required,
            "status": "ok",
            "parsed": None,
            "raw_file": None,
            "error": None,
        }

        try:
            response = client.ask(task.query)
            parsed = extract_key_data(response)

            # Сохраняем полный ответ API для проверки и отчета.
            filename = f"{task.id:02d}_{_slugify(task.query)}.json"
            raw_file = raw_dir / filename
            _save_json(raw_file, response)

            result_item["parsed"] = parsed
            result_item["raw_file"] = str(raw_file)

            if not parsed["success"]:
                result_item["status"] = "api_no_result"

        except Exception as exc:  # noqa: BLE001
            # Фиксируем ошибку, но продолжаем выполнение остальных запросов.
            logger.error("Failed to process query '%s': %s", task.query, exc)
            result_item["status"] = "error"
            result_item["error"] = str(exc)

        extracted_results.append(result_item)

    extracted_file = output_dir / "extracted_results.json"
    report_file = output_dir / "human_readable_report.txt"

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_queries": len(tasks),
        "results": extracted_results,
    }

    # Сохраняем итоговые файлы: JSON и текстовый отчет.
    _save_json(extracted_file, payload)
    _save_report(report_file, extracted_results)

    logger.info("All queries finished")
    logger.info("Extracted results saved to %s", extracted_file)
    logger.info("Human-readable report saved to %s", report_file)

    return RunArtifacts(extracted_file=extracted_file, report_file=report_file, raw_dir=raw_dir)
