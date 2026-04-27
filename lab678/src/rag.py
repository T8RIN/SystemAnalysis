from __future__ import annotations

import json
import re
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
        candidate_count = min(50, max(top_k * 4, top_k + 6))
        candidates = self.repository.similarity_search(
            question_embedding,
            top_k=candidate_count,
            source=source,
        )
        results = rerank_results(cleaned_question, candidates)[:top_k]
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
    for index, result in enumerate(results, start=1):
        source = result.metadata.get("source", "unknown")
        parts.append(f"[{index}] Источник: {source}; id: {result.id}\n{result.content}")
    return "\n\n---\n\n".join(parts)


def build_prompt(context: str, question: str) -> str:
    return f"""Контекст ниже отсортирован по релевантности: фрагмент [1] самый важный.
Используя только информацию из контекста ниже, ответь на вопрос.
Если первый фрагмент прямо отвечает на вопрос, опирайся на него.
Не подменяй ответ сведениями из менее релевантных фрагментов.
Если в контексте нет ответа, скажи "Не знаю".

Контекст:
{context}

Вопрос: {question}

Ответ:"""


STOP_WORDS = {
    "а",
    "в",
    "и",
    "к",
    "о",
    "об",
    "он",
    "по",
    "с",
    "у",
    "что",
    "это",
    "кто",
    "такое",
    "такой",
    "такого",
    "такую",
    "такая",
    "такие",
    "какой",
    "какая",
    "где",
    "как",
    "почему",
    "зачем",
    "расскажи",
    "работает",
    "работают",
    "работать",
    "про",
    "для",
    "или",
    "его",
    "ее",
}


def rerank_results(question: str, results: list[SearchResult]) -> list[SearchResult]:
    if not results:
        return []
    scored = [(result, _lexical_score(question, result)) for result in results]
    max_lexical = max(lexical for _, lexical in scored)
    if max_lexical >= 1.0:
        scored = [(result, lexical) for result, lexical in scored if lexical > 0.25]
    elif max_lexical >= 0.3:
        scored = [(result, lexical) for result, lexical in scored if lexical > 0.1]
    ranked = [_with_rerank_score(result, lexical) for result, lexical in scored]
    return sorted(ranked, key=lambda result: result.score, reverse=True)


def _with_rerank_score(result: SearchResult, lexical_score: float) -> SearchResult:
    return SearchResult(
        id=result.id,
        content=result.content,
        metadata=result.metadata,
        created_at=result.created_at,
        distance=result.distance,
        score=min(1.0, max(0.0, result.score + lexical_score / 4.0)),
    )


def _lexical_score(question: str, result: SearchResult) -> float:
    query_terms = set(_terms(question))
    content_terms = set(_terms(result.content))
    metadata_text = json.dumps(result.metadata or {}, ensure_ascii=False)
    metadata_terms = set(_terms(metadata_text))
    haystack = _normalize(f"{result.content} {metadata_text}")

    score = 0.0
    if query_terms:
        overlap = query_terms.intersection(content_terms.union(metadata_terms))
        score += min(1.0, len(overlap) / len(query_terms)) * 0.7

    for surname, initials in _surname_initial_targets(question):
        if _metadata_matches_person(result.metadata, surname, initials):
            score += 2.2
        if _content_has_full_name(result.content, surname, initials):
            score += 2.0
        if haystack.startswith(surname):
            score += 0.8
        if re.search(rf"\b{re.escape(surname)}\w*\b", haystack):
            score += 0.25
        if re.search(rf"\bколлег\w*\s+{re.escape(surname)}\w*\b", haystack):
            score -= 0.8

    return score


def _normalize(text: str) -> str:
    lowered = text.lower().replace("ё", "е")
    return re.sub(r"[^0-9a-zа-я]+", " ", lowered).strip()


def _terms(text: str) -> list[str]:
    return [
        token
        for token in _normalize(text).split()
        if len(token) > 1 and token not in STOP_WORDS
    ]


def _surname_initial_targets(question: str) -> list[tuple[str, tuple[str, str]]]:
    tokens = _normalize(question).split()
    targets: list[tuple[str, tuple[str, str]]] = []
    for index in range(len(tokens) - 2):
        surname = tokens[index]
        first_initial = tokens[index + 1]
        second_initial = tokens[index + 2]
        if (
            len(surname) > 2
            and surname not in STOP_WORDS
            and len(first_initial) == 1
            and len(second_initial) == 1
        ):
            targets.append((surname, (first_initial, second_initial)))
    return targets


def _metadata_matches_person(metadata: dict[str, Any], surname: str, initials: tuple[str, str]) -> bool:
    values = []
    for key in ("person", "subject", "name", "aliases"):
        value = metadata.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value:
            values.append(str(value))
    return any(_text_matches_name(value, surname, initials) for value in values)


def _content_has_full_name(content: str, surname: str, initials: tuple[str, str]) -> bool:
    tokens = _normalize(content).split()
    for index in range(len(tokens) - 2):
        token = tokens[index]
        first_name = tokens[index + 1]
        patronymic = tokens[index + 2]
        surname_matches = token == surname or token.startswith(surname) or surname.startswith(token)
        if not surname_matches:
            continue
        if len(first_name) <= 1 or len(patronymic) <= 1:
            continue
        if first_name.startswith(initials[0]) and patronymic.startswith(initials[1]):
            return True
    return False


def _text_matches_name(text: str, surname: str, initials: tuple[str, str]) -> bool:
    normalized = _normalize(text)
    if surname not in normalized:
        return False
    tokens = normalized.split()
    for index, token in enumerate(tokens):
        if token != surname and not token.startswith(surname):
            continue
        if index + 2 >= len(tokens):
            continue
        if tokens[index + 1].startswith(initials[0]) and tokens[index + 2].startswith(initials[1]):
            return True
    return False
