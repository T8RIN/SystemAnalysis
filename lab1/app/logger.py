import logging
from pathlib import Path


def setup_logger(log_file: Path) -> logging.Logger:
    # Создаем директорию под лог, если она отсутствует.
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("lab1")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Пишем логи одновременно в файл и в консоль.
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
