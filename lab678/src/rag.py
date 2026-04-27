from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import AppConfig
from .database import RagRepository, SearchResult
from .embeddings import EmbeddingModel
from .llm import LocalLLMClient


@dataclass(frozen=True)
class RagAnswer:
    question: str
    answer: str
    context: str
    prompt: str
    results: list[SearchResult]


class RagService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.repository = RagRepository(config)
        self.repository.connect()
        self.repository.ensure_schema(config.vector_dimension)
        self.embedder = EmbeddingModel(config.embedding_model, config.vector_dimension)
        self.llm = LocalLLMClient(
            base_url=config.lm_studio_url,
            model=config.llm_model,
            timeout=config.llm_timeout,
            max_tokens=config.llm_max_tokens,
            temperature=config.llm_temperature,
        )

    def close(self) -> None:
        self.repository.close()

    def index_document(self, content: str, metadata: dict[str, Any] | None = None) -> int:
        cleaned = content.strip()
        if not cleaned:
            raise ValueError("Нельзя добавить пустой документ.")
        embedding = self.embedder.encode(cleaned)
        return self.repository.insert_document(cleaned, embedding, metadata or {})

    def update_document(
        self,
        document_id: int,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        cleaned = content.strip()
        if not cleaned:
            raise ValueError("Текст документа не может быть пустым.")
        embedding = self.embedder.encode(cleaned)
        return self.repository.update_document(document_id, cleaned, embedding, metadata or {})

    def ask(self, question: str, top_k: int = 3, source: str | None = None, use_llm: bool = True) -> RagAnswer:
        cleaned_question = question.strip()
        if not cleaned_question:
            raise ValueError("Вопрос не может быть пустым.")
        question_embedding = self.embedder.encode(cleaned_question)
        results = self.repository.similarity_search(question_embedding, top_k=top_k, source=source)
        if not results:
            return RagAnswer(
                question=cleaned_question,
                answer="Не найдено релевантных документов.",
                context="",
                prompt="",
                results=[],
            )

        context = build_context(results)
        prompt = build_prompt(context, cleaned_question)
        if not use_llm:
            answer = "LLM отключена. Ниже показаны найденные фрагменты контекста."
        else:
            try:
                answer = self.llm.complete(prompt)
            except RuntimeError as exc:
                answer = f"Локальная LLM недоступна: {exc}"
        return RagAnswer(
            question=cleaned_question,
            answer=answer,
            context=context,
            prompt=prompt,
            results=results,
        )


def build_context(results: list[SearchResult]) -> str:
    parts = []
    for result in results:
        source = result.metadata.get("source", "unknown")
        parts.append(f"[Источник: {source}; id: {result.id}]\n{result.content}")
    return "\n\n---\n\n".join(parts)


def build_prompt(context: str, question: str) -> str:
    return f"""Используя только информацию из контекста ниже, ответь на вопрос.
Если в контексте нет ответа, скажи "Не знаю".

Контекст:
{context}

Вопрос: {question}

Ответ:"""
