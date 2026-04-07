from pathlib import Path

from app.config import load_config
from app.logger import setup_logger
from app.queries import get_queries
from app.runner import run_queries
from app.wolfram_client import WolframClient


def main() -> None:
    # Определяем корневую директорию проекта и читаем конфигурацию.
    root_dir = Path(__file__).resolve().parent
    config = load_config(root_dir / "config.json")

    # Настраиваем логирование в файл и консоль.
    logger = setup_logger(config.log_file)
    logger.info("Starting Wolfram Alpha lab runner")

    # Создаем клиент API с таймаутом и количеством повторных попыток.
    client = WolframClient(
        appid=config.appid,
        base_url=config.base_url,
        timeout_seconds=config.timeout_seconds,
        max_retries=config.max_retries,
        logger=logger,
    )

    # Последовательно выполняем запросы и сохраняем артефакты запуска.
    tasks = get_queries()
    artifacts = run_queries(client=client, tasks=tasks, output_dir=config.output_dir, logger=logger)

    print("Lab 1 completed successfully")
    print(f"Total queries: {len(tasks)}")
    print(f"Extracted data file: {artifacts.extracted_file}")
    print(f"Human-readable report: {artifacts.report_file}")
    print(f"Raw API responses folder: {artifacts.raw_dir}")


if __name__ == "__main__":
    main()
