from __future__ import annotations

import argparse

from src.config import get_config
from src.rag import RagService
from src.sample_data import SAMPLE_DOCUMENTS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CLI-демо RAG-системы на PostgreSQL и pgvector.")
    parser.add_argument(
        "--question",
        default="Кто такой Бурнашев Р.А.?",
        help="Вопрос к RAG-системе.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Количество фрагментов контекста для поиска.",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Не очищать таблицу documents перед демо-запуском.",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Не добавлять тестовые документы.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Только найти контекст, без запроса к локальной LLM.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = get_config()
    try:
        service = RagService(config)
    except Exception as exc:
        print("Не удалось запустить RAG-систему.")
        print(f"Причина: {exc}")
        print("Проверьте PostgreSQL с pgvector, файл .env и сервер LM Studio.")
        raise SystemExit(1) from exc
    top_k = args.top_k or config.default_top_k

    try:
        print("Таблица и индекс готовы")
        print(f"Модель эмбеддингов: {config.embedding_model}")

        if not args.keep_db:
            service.repository.truncate()
            print("Таблица documents очищена")

        if not args.no_seed:
            for content, metadata in SAMPLE_DOCUMENTS:
                document_id = service.index_document(content, metadata)
                print(f"Документ добавлен: id={document_id}, source={metadata.get('source')}")

        print(f"\nВопрос: {args.question}")
        answer = service.ask(args.question, top_k=top_k, use_llm=not args.no_llm)

        print("\nНайденный контекст:")
        for result in answer.results:
            source = result.metadata.get("source", "unknown")
            print(f"- id={result.id}; source={source}; score={result.score:.3f}")
            print(f"  {result.content[:180]}")

        print(f"\nОтвет:\n{answer.answer}")
    finally:
        service.close()


if __name__ == "__main__":
    main()
