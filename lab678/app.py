from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from src.config import get_config
from src.rag import RagService
from src.sample_data import SAMPLE_DOCUMENTS
from src.text_utils import split_text


st.set_page_config(
    page_title="Lab 6-8 RAG",
    layout="wide",
)


@st.cache_resource(show_spinner="Загрузка модели эмбеддингов и подключение к PostgreSQL...")
def load_service() -> RagService:
    return RagService(get_config())


def parse_metadata(raw_text: str) -> dict[str, Any]:
    raw_text = raw_text.strip()
    if not raw_text:
        return {}
    value = json.loads(raw_text)
    if not isinstance(value, dict):
        raise ValueError("metadata должен быть JSON-объектом.")
    return value


def documents_to_frame(documents: list[Any]) -> pd.DataFrame:
    rows = []
    for document in documents:
        metadata = document.metadata or {}
        rows.append(
            {
                "id": document.id,
                "source": metadata.get("source", "unknown"),
                "topic": metadata.get("topic", ""),
                "content": document.content,
                "created_at": document.created_at,
            }
        )
    return pd.DataFrame(rows)


def results_to_frame(results: list[Any]) -> pd.DataFrame:
    rows = []
    for result in results:
        metadata = result.metadata or {}
        rows.append(
            {
                "id": result.id,
                "source": metadata.get("source", "unknown"),
                "score": round(result.score, 4),
                "distance": round(result.distance, 4),
                "content": result.content,
            }
        )
    return pd.DataFrame(rows)


def import_json(payload: bytes, fallback_source: str) -> list[tuple[str, dict[str, Any]]]:
    data = json.loads(payload.decode("utf-8"))
    if isinstance(data, dict):
        data = data.get("documents", [])
    if not isinstance(data, list):
        raise ValueError("JSON должен быть списком документов или объектом с ключом documents.")

    documents = []
    for item in data:
        if isinstance(item, str):
            documents.append((item, {"source": fallback_source}))
            continue
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or item.get("text") or "").strip()
        if not content:
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        metadata = dict(metadata)
        metadata.setdefault("source", item.get("source") or fallback_source)
        if item.get("topic"):
            metadata.setdefault("topic", item.get("topic"))
        documents.append((content, metadata))
    return documents


def show_retrieval(answer_frame: pd.DataFrame) -> None:
    if answer_frame.empty:
        return
    st.dataframe(answer_frame, use_container_width=True, hide_index=True)
    chart_frame = answer_frame[["id", "score"]].copy()
    chart_frame["id"] = chart_frame["id"].astype(str)
    st.bar_chart(chart_frame.set_index("id"))


try:
    service = load_service()
except Exception as exc:
    st.title("RAG-система")
    st.error(str(exc))
    st.stop()

config = get_config()
st.title("RAG-система PostgreSQL + pgvector + локальная LLM")

total_documents = service.repository.count_documents()
sources = service.repository.sources()
col_total, col_sources, col_model = st.columns([1, 1, 2])
col_total.metric("Документы", total_documents)
col_sources.metric("Источники", len(sources))
col_model.metric("Эмбеддинги", config.embedding_model.split("/")[-1])

tab_rag, tab_kb, tab_import, tab_status = st.tabs(
    ["RAG-запрос", "База знаний", "Импорт", "Состояние"]
)

with tab_rag:
    left, right = st.columns([2, 1])
    with left:
        question = st.text_area("Вопрос", value="Кто такой Бурнашев Р.А.?", height=96)
    with right:
        top_k = st.slider("top_k", min_value=1, max_value=10, value=config.default_top_k)
        source_options = ["Все источники"] + sources
        source_choice = st.selectbox("Источник", source_options)
        use_llm = st.toggle("Запрашивать LLM", value=True)

    if st.button("Ответить", type="primary", use_container_width=True):
        source_filter = None if source_choice == "Все источники" else source_choice
        with st.spinner("Ищу контекст и формирую ответ..."):
            answer = service.ask(question, top_k=top_k, source=source_filter, use_llm=use_llm)
        st.subheader("Ответ")
        st.write(answer.answer)
        st.subheader("Результаты поиска")
        show_retrieval(results_to_frame(answer.results))
        with st.expander("Промпт"):
            st.code(answer.prompt or "Промпт не сформирован.", language="text")

with tab_kb:
    add_col, edit_col = st.columns([1, 1])

    with add_col:
        st.subheader("Добавить факт")
        with st.form("add_document"):
            new_content = st.text_area("Текст", height=160)
            new_source = st.text_input("source", value="manual")
            new_topic = st.text_input("topic", value="")
            submitted = st.form_submit_button("Добавить", type="primary")
        if submitted:
            metadata = {"source": new_source.strip() or "manual"}
            if new_topic.strip():
                metadata["topic"] = new_topic.strip()
            try:
                document_id = service.index_document(new_content, metadata)
                st.success(f"Документ добавлен: id={document_id}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with edit_col:
        st.subheader("Редактировать факт")
        selected_id = st.number_input("ID", min_value=1, step=1)
        selected_doc = service.repository.get_document(int(selected_id))
        if selected_doc:
            with st.form("edit_document"):
                edit_content = st.text_area("Текст документа", value=selected_doc.content, height=160)
                edit_metadata = st.text_area(
                    "metadata JSON",
                    value=json.dumps(selected_doc.metadata, ensure_ascii=False, indent=2),
                    height=120,
                )
                save_clicked = st.form_submit_button("Сохранить", type="primary")
            if save_clicked:
                try:
                    metadata = parse_metadata(edit_metadata)
                    service.update_document(int(selected_id), edit_content, metadata)
                    st.success("Документ обновлен")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

            if st.button("Удалить выбранный документ", use_container_width=True):
                service.repository.delete_document(int(selected_id))
                st.warning("Документ удален")
                st.rerun()
        else:
            st.info("Документ с таким ID не найден.")

    st.subheader("Поиск по базе")
    query = st.text_input("Строка поиска")
    documents = service.repository.list_documents(query=query, limit=300)
    st.dataframe(documents_to_frame(documents), use_container_width=True, hide_index=True)

    stats = pd.DataFrame(service.repository.stats_by_source())
    if not stats.empty:
        st.subheader("Распределение по источникам")
        st.bar_chart(stats.set_index("source"))

with tab_import:
    st.subheader("Загрузка фактов")
    uploaded = st.file_uploader("Файл", type=["txt", "md", "json", "csv"])
    import_source = st.text_input("source для импорта", value="uploaded")
    chunk_size = st.slider("Размер фрагмента", min_value=300, max_value=2000, value=900, step=100)

    if uploaded is not None:
        suffix = uploaded.name.rsplit(".", maxsplit=1)[-1].lower()
        if suffix in {"txt", "md"}:
            text = uploaded.getvalue().decode("utf-8")
            chunks = split_text(text, max_chars=chunk_size)
            st.write(f"Фрагментов: {len(chunks)}")
            if chunks:
                st.dataframe(pd.DataFrame({"content": chunks}), use_container_width=True)
            if st.button("Импортировать текст", type="primary"):
                for index, chunk in enumerate(chunks, start=1):
                    service.index_document(
                        chunk,
                        {"source": import_source.strip() or "uploaded", "chunk": index},
                    )
                st.success(f"Импортировано фрагментов: {len(chunks)}")
                st.rerun()

        elif suffix == "json":
            try:
                items = import_json(uploaded.getvalue(), import_source.strip() or "uploaded")
                st.write(f"Документов: {len(items)}")
                st.dataframe(
                    pd.DataFrame(
                        [{"content": content, "metadata": metadata} for content, metadata in items]
                    ),
                    use_container_width=True,
                )
                if st.button("Импортировать JSON", type="primary"):
                    for content, metadata in items:
                        service.index_document(content, metadata)
                    st.success(f"Импортировано документов: {len(items)}")
                    st.rerun()
            except Exception as exc:
                st.error(str(exc))

        elif suffix == "csv":
            frame = pd.read_csv(uploaded)
            st.dataframe(frame.head(20), use_container_width=True)
            content_column = st.selectbox("Колонка с текстом", list(frame.columns))
            source_column_options = ["Не использовать"] + list(frame.columns)
            source_column = st.selectbox("Колонка source", source_column_options)
            if st.button("Импортировать CSV", type="primary"):
                imported = 0
                for _, row in frame.iterrows():
                    content = str(row.get(content_column, "")).strip()
                    if not content:
                        continue
                    metadata = {"source": import_source.strip() or "uploaded"}
                    if source_column != "Не использовать":
                        metadata["source"] = str(row.get(source_column) or metadata["source"])
                    service.index_document(content, metadata)
                    imported += 1
                st.success(f"Импортировано строк: {imported}")
                st.rerun()

with tab_status:
    st.subheader("Конфигурация")
    st.json(
        {
            "db": f"{config.db_host}:{config.db_port}/{config.db_name}",
            "embedding_model": config.embedding_model,
            "vector_dimension": config.vector_dimension,
            "lm_studio_url": config.lm_studio_url,
            "llm_model": config.llm_model or "auto",
        }
    )

    models = service.llm.list_models()
    if models:
        st.success("LLM-сервер отвечает")
        st.write(models)
    else:
        st.warning("LLM-сервер не вернул список моделей")

    action_col, clear_col = st.columns([1, 1])
    with action_col:
        if st.button("Добавить тестовые факты", use_container_width=True):
            for content, metadata in SAMPLE_DOCUMENTS:
                service.index_document(content, metadata)
            st.success("Тестовые факты добавлены")
            st.rerun()
    with clear_col:
        confirm_clear = st.checkbox("Подтвердить очистку базы")
        if st.button("Очистить documents", disabled=not confirm_clear, use_container_width=True):
            service.repository.truncate()
            st.warning("Таблица documents очищена")
            st.rerun()
