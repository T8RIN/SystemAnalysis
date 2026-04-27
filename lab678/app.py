from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from src.config import ENV_PATH, AppConfig, get_config
from src.rag import RagAnswer, RagService
from src.sample_data import SAMPLE_DOCUMENTS
from src.text_utils import split_text


st.set_page_config(
    page_title="Lab 6-8 RAG Studio",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def inject_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #0f131a;
            --panel: #151b24;
            --panel-2: #1b2430;
            --line: #2b3544;
            --text: #f4f7fb;
            --muted: #a8b3c2;
            --cyan: #42d3bd;
            --cyan-2: #70decf;
            --rose: #ff7474;
            --gold: #f5bd4f;
            --blue: #7aa8ff;
            --violet: #9b8cff;
        }

        .stApp {
            background: var(--bg);
            color: var(--text);
        }

        .block-container {
            padding-top: 2.4rem;
            padding-bottom: 2rem;
            max-width: 1320px;
        }

        h1, h2, h3 {
            letter-spacing: 0;
            line-height: 1.22;
        }

        div[data-testid="stMetric"] {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 0.75rem 0.9rem;
            min-height: 92px;
        }

        div[data-testid="stTabs"] button {
            border-radius: 6px;
            padding: 0.55rem 0.8rem;
            font-weight: 650;
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            color: #dbe4ee !important;
        }

        div[data-testid="stTabs"] button[aria-selected="true"] {
            border-bottom: 3px solid var(--cyan);
            color: #ffffff;
        }

        .hero {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 1.25rem 1.15rem 1rem;
            background: var(--panel);
            margin-bottom: 0.9rem;
            overflow: visible;
        }

        .hero-title {
            font-size: 1.65rem;
            font-weight: 780;
            line-height: 1.22;
            margin: 0 0 0.35rem 0;
            letter-spacing: 0;
        }

        .hero-subtitle {
            color: var(--muted);
            font-size: 0.98rem;
            margin: 0;
        }

        .status-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.9rem;
        }

        .pill {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 999px;
            color: #d7dee9;
            background: rgba(255, 255, 255, 0.04);
            padding: 0.35rem 0.62rem;
            font-size: 0.86rem;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--line);
            background: rgba(21, 27, 36, 0.72);
            border-radius: 8px;
        }

        html body .stApp .stButton button[data-testid^="stBaseButton"],
        html body .stApp .stDownloadButton button[data-testid^="stBaseButton"],
        html body .stApp div[data-testid="stFileUploader"] button[data-testid^="stBaseButton"],
        html body .stApp div[data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton"],
        button[kind="primary"],
        button[kind="secondary"] {
            background: linear-gradient(135deg, var(--cyan-2) 0%, #6bb7ff 52%, var(--violet) 100%) !important;
            background-color: var(--cyan-2) !important;
            background-image: linear-gradient(135deg, var(--cyan-2) 0%, #6bb7ff 52%, var(--violet) 100%) !important;
            border: 1px solid rgba(191, 245, 255, 0.42) !important;
            color: #07111f !important;
            border-radius: 8px !important;
            font-weight: 750 !important;
            min-height: 2.65rem !important;
            box-shadow: 0 10px 24px rgba(66, 211, 189, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.36) !important;
            text-shadow: none !important;
        }

        html body .stApp .stButton button[data-testid^="stBaseButton"] *,
        html body .stApp .stDownloadButton button[data-testid^="stBaseButton"] *,
        html body .stApp div[data-testid="stFileUploader"] button[data-testid^="stBaseButton"] *,
        html body .stApp div[data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton"] *,
        button[kind="primary"] *,
        button[kind="secondary"] * {
            color: #07111f !important;
        }

        html body .stApp .stButton button[data-testid^="stBaseButton"]:hover,
        html body .stApp .stDownloadButton button[data-testid^="stBaseButton"]:hover,
        html body .stApp div[data-testid="stFileUploader"] button[data-testid^="stBaseButton"]:hover,
        html body .stApp div[data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton"]:hover,
        button[kind="primary"]:hover {
            border-color: rgba(230, 255, 255, 0.78) !important;
            filter: brightness(1.07) saturate(1.08);
            transform: translateY(-1px);
        }

        html body .stApp .stButton button[data-testid^="stBaseButton"]:disabled,
        html body .stApp .stDownloadButton button[data-testid^="stBaseButton"]:disabled,
        html body .stApp div[data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton"]:disabled,
        html body .stApp div[data-testid="stFileUploader"] button[data-testid^="stBaseButton"]:disabled {
            background: linear-gradient(135deg, #1b2330 0%, #242b38 100%) !important;
            background-color: #1b2330 !important;
            background-image: linear-gradient(135deg, #1b2330 0%, #242b38 100%) !important;
            border-color: #344052 !important;
            color: #8f9aa9 !important;
            box-shadow: none !important;
            transform: none !important;
            opacity: 1 !important;
        }

        html body .stApp .stButton button[data-testid^="stBaseButton"]:disabled *,
        html body .stApp .stDownloadButton button[data-testid^="stBaseButton"]:disabled *,
        html body .stApp div[data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton"]:disabled *,
        html body .stApp div[data-testid="stFileUploader"] button[data-testid^="stBaseButton"]:disabled * {
            color: #8f9aa9 !important;
        }

        .note-panel {
            border: 1px solid var(--line);
            background: var(--panel);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 1rem;
        }

        .answer {
            border-left: 4px solid var(--cyan);
            border-radius: 8px;
            background: var(--panel);
            border-top: 1px solid var(--line);
            border-right: 1px solid var(--line);
            border-bottom: 1px solid var(--line);
            padding: 1rem 1.1rem;
            margin: 0.5rem 0 1rem 0;
            color: #f5fbff;
            font-size: 1.04rem;
            line-height: 1.55;
        }

        .doc-card {
            border: 1px solid var(--line);
            background: var(--panel);
            border-radius: 8px;
            padding: 0.9rem 1rem;
            margin-bottom: 0.75rem;
        }

        .doc-meta {
            display: flex;
            justify-content: space-between;
            gap: 0.75rem;
            color: var(--muted);
            font-size: 0.86rem;
            margin-bottom: 0.55rem;
        }

        .doc-text {
            color: #eef5ff;
            line-height: 1.5;
        }

        .accent-cyan { color: var(--cyan); }
        .accent-rose { color: var(--rose); }
        .accent-gold { color: var(--gold); }
        .muted { color: var(--muted); }

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--line);
            border-radius: 8px;
            overflow: hidden;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner="Подключаю PostgreSQL и загружаю модель эмбеддингов...")
def load_service(config_key: str) -> RagService:
    del config_key
    return RagService(get_config())


def service_cache_key(config: AppConfig) -> str:
    parts = [
        config.db_host,
        str(config.db_port),
        config.db_name,
        config.db_user,
        config.embedding_model,
        str(config.vector_dimension),
        config.lm_studio_url,
        config.llm_model or "",
    ]
    return "|".join(parts)


def sync_runtime_settings(service: RagService, config: AppConfig) -> None:
    service.llm.timeout = config.llm_timeout
    service.llm.max_tokens = config.llm_max_tokens
    service.llm.temperature = config.llm_temperature


def parse_metadata(raw_text: str) -> dict[str, Any]:
    raw_text = raw_text.strip()
    if not raw_text:
        return {}
    value = json.loads(raw_text)
    if not isinstance(value, dict):
        raise ValueError("metadata должен быть JSON-объектом.")
    return value


def make_metadata(source: str, topic: str, raw_json: str = "") -> dict[str, Any]:
    metadata = parse_metadata(raw_json) if raw_json.strip() else {}
    metadata["source"] = source.strip() or metadata.get("source") or "manual"
    if topic.strip():
        metadata["topic"] = topic.strip()
    return metadata


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


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
                "metadata": json.dumps(metadata, ensure_ascii=False),
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


def stats_frame(service: RagService) -> pd.DataFrame:
    frame = pd.DataFrame(service.repository.stats_by_source())
    if frame.empty:
        return pd.DataFrame(columns=["source", "total"])
    frame["total"] = frame["total"].astype(int)
    return frame


def topic_frame(documents: list[Any]) -> pd.DataFrame:
    topics: dict[str, int] = {}
    for document in documents:
        topic = str((document.metadata or {}).get("topic") or "unknown")
        topics[topic] = topics.get(topic, 0) + 1
    return pd.DataFrame(
        [{"topic": topic, "total": total} for topic, total in sorted(topics.items())]
    )


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


def save_env_values(path: Path, updates: dict[str, str]) -> None:
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    remaining = dict(updates)
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            result.append(line.rstrip())
            continue
        key = line.split("=", maxsplit=1)[0].strip()
        if key in remaining:
            result.append(f"{key}={remaining.pop(key)}")
        else:
            result.append(line.rstrip())

    for key, value in remaining.items():
        result.append(f"{key}={value}")

    path.write_text("\n".join(result).rstrip() + "\n", encoding="utf-8")
    for key, value in updates.items():
        os.environ[key] = value


def render_header(config: AppConfig, total_documents: int, sources: list[str], models: list[str]) -> None:
    model_status = "LLM подключена" if models else "LLM не отвечает"
    st.markdown(
        f"""
        <div class="hero">
            <div class="hero-title">Lab 6-8 RAG Studio</div>
            <p class="hero-subtitle">PostgreSQL + pgvector + локальная LLM для поиска, ответов и управления базой знаний.</p>
            <div class="status-row">
                <span class="pill"><span class="accent-cyan">PostgreSQL</span> {escape(config.db_host)}:{config.db_port}</span>
                <span class="pill"><span class="accent-gold">pgvector</span> vector({config.vector_dimension})</span>
                <span class="pill"><span class="accent-rose">LLM</span> {escape(config.llm_model or "auto")}</span>
                <span class="pill">{escape(model_status)}</span>
                <span class="pill">{total_documents} документов</span>
                <span class="pill">{len(sources)} источников</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_answer(answer: RagAnswer) -> None:
    st.markdown("### Ответ")
    st.markdown(
        f'<div class="answer">{escape(answer.answer).replace(chr(10), "<br>")}</div>',
        unsafe_allow_html=True,
    )
    if not answer.results:
        return

    frame = results_to_frame(answer.results)
    chart_frame = frame[["id", "score"]].copy()
    chart_frame["id"] = chart_frame["id"].astype(str)

    left, right = st.columns([1.25, 1])
    with left:
        st.markdown("### Найденный контекст")
        for result in answer.results:
            source = result.metadata.get("source", "unknown")
            topic = result.metadata.get("topic", "")
            topic_text = f" / {escape(topic)}" if topic else ""
            st.markdown(
                f"""
                <div class="doc-card">
                    <div class="doc-meta">
                        <span>id {result.id} / {escape(source)}{topic_text}</span>
                        <span>score {result.score:.3f}</span>
                    </div>
                    <div class="doc-text">{escape(result.content)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    with right:
        st.markdown("### Релевантность")
        st.bar_chart(chart_frame.set_index("id"))
        st.dataframe(frame, width="stretch", hide_index=True)

    with st.expander("Промпт для локальной LLM"):
        st.code(answer.prompt or "Промпт не сформирован.", language="text")


def render_rag_tab(service: RagService, config: AppConfig, sources: list[str]) -> None:
    with st.container(border=True):
        query_col, control_col = st.columns([2.2, 1], vertical_alignment="bottom")
        with query_col:
            question = st.text_area(
                "Вопрос к базе знаний",
                value=st.session_state.get("last_question", "Кто такой Бурнашев Р.А.?"),
                height=132,
                placeholder="Введите вопрос, на который нужно ответить по документам...",
            )
        with control_col:
            top_k = st.slider(
                "Количество фрагментов top_k",
                min_value=1,
                max_value=10,
                value=min(max(config.default_top_k, 1), 10),
            )
            source_options = ["Все источники"] + sources
            source_choice = st.selectbox("Фильтр источника", source_options)
            use_llm = st.checkbox("Генерировать ответ LLM", value=True)
            ask_clicked = st.button("Сформировать ответ", type="primary", width="stretch")

    if ask_clicked:
        source_filter = None if source_choice == "Все источники" else source_choice
        st.session_state["last_question"] = question
        with st.spinner("Ищу релевантные факты и собираю ответ..."):
            st.session_state["last_answer"] = service.ask(
                question,
                top_k=top_k,
                source=source_filter,
                use_llm=use_llm,
            )

    if "last_answer" in st.session_state:
        render_answer(st.session_state["last_answer"])


def render_knowledge_tab(service: RagService, sources: list[str]) -> None:
    add_col, edit_col = st.columns([1, 1])

    with add_col:
        st.markdown("### Новый факт")
        with st.form("add_document", clear_on_submit=True):
            new_content = st.text_area("Текст факта", height=170)
            meta_cols = st.columns([1, 1])
            with meta_cols[0]:
                new_source = st.text_input("source", value="manual")
            with meta_cols[1]:
                new_topic = st.text_input("topic", value="")
            extra_metadata = st.text_area("Дополнительный metadata JSON", value="", height=90)
            submitted = st.form_submit_button("Добавить в базу знаний", type="primary")
        if submitted:
            try:
                metadata = make_metadata(new_source, new_topic, extra_metadata)
                document_id = service.index_document(new_content, metadata)
                st.success(f"Документ добавлен: id={document_id}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with edit_col:
        st.markdown("### Редактирование")
        selected_id = st.number_input("ID документа", min_value=1, step=1)
        selected_doc = service.repository.get_document(int(selected_id))
        if selected_doc:
            with st.form("edit_document"):
                edit_content = st.text_area("Текст документа", value=selected_doc.content, height=170)
                edit_metadata = st.text_area(
                    "metadata JSON",
                    value=json.dumps(selected_doc.metadata, ensure_ascii=False, indent=2),
                    height=120,
                )
                save_clicked = st.form_submit_button("Сохранить изменения", type="primary")
            if save_clicked:
                try:
                    metadata = parse_metadata(edit_metadata)
                    service.update_document(int(selected_id), edit_content, metadata)
                    st.success("Документ обновлен")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

            confirm_delete = st.checkbox("Подтвердить удаление выбранного документа")
            if st.button("Удалить документ", disabled=not confirm_delete, width="stretch"):
                service.repository.delete_document(int(selected_id))
                st.warning("Документ удален")
                st.rerun()
        else:
            st.info("Документ с таким ID не найден.")

    st.markdown("### Поиск и просмотр")
    search_col, source_col, mode_col = st.columns([2, 1, 1])
    with search_col:
        query = st.text_input("Строковый поиск по content и metadata")
    with source_col:
        source_filter = st.selectbox("Источник", ["Все"] + sources, key="kb_source")
    with mode_col:
        limit = st.number_input("Лимит", min_value=20, max_value=500, value=200, step=20)

    documents = service.repository.list_documents(query=query, limit=int(limit))
    if source_filter != "Все":
        documents = [
            document
            for document in documents
            if (document.metadata or {}).get("source") == source_filter
        ]
    frame = documents_to_frame(documents)
    st.dataframe(frame, width="stretch", hide_index=True, height=360)

    st.markdown("### Семантический поиск")
    semantic_cols = st.columns([2, 1])
    with semantic_cols[0]:
        semantic_query = st.text_input("Смысловой запрос", value="экспертные системы и машинное обучение")
    with semantic_cols[1]:
        semantic_k = st.slider("top_k для поиска", 1, 10, 5, key="semantic_k")
    if st.button("Найти похожие факты", width="stretch"):
        source = None if source_filter == "Все" else source_filter
        answer = service.ask(semantic_query, top_k=semantic_k, source=source, use_llm=False)
        st.dataframe(results_to_frame(answer.results), width="stretch", hide_index=True)


def render_import_tab(service: RagService) -> None:
    st.markdown("### Импорт фактов")
    settings_col, preview_col = st.columns([1, 1.4])
    with settings_col:
        uploaded = st.file_uploader("Файл", type=["txt", "md", "json", "csv"])
        import_source = st.text_input("source для импорта", value="uploaded")
        import_topic = st.text_input("topic для импорта", value="")
        chunk_size = st.slider("Размер текстового фрагмента", 300, 2000, 900, step=100)
    with preview_col:
        st.markdown(
            '<div class="note-panel"><span class="muted">Поддерживаются txt, md, json и csv. '
            "Для длинного текста включается автоматическое разбиение на фрагменты.</span></div>",
            unsafe_allow_html=True,
        )

    if uploaded is None:
        return

    suffix = uploaded.name.rsplit(".", maxsplit=1)[-1].lower()
    source = import_source.strip() or "uploaded"
    topic = import_topic.strip()

    if suffix in {"txt", "md"}:
        text = uploaded.getvalue().decode("utf-8")
        chunks = split_text(text, max_chars=chunk_size)
        st.metric("Фрагментов к импорту", len(chunks))
        st.dataframe(pd.DataFrame({"content": chunks}), width="stretch", height=320)
        if st.button("Импортировать текст", type="primary", width="stretch"):
            for index, chunk in enumerate(chunks, start=1):
                metadata = {"source": source, "chunk": index}
                if topic:
                    metadata["topic"] = topic
                service.index_document(chunk, metadata)
            st.success(f"Импортировано фрагментов: {len(chunks)}")
            st.rerun()

    elif suffix == "json":
        try:
            items = import_json(uploaded.getvalue(), source)
            if topic:
                items = [
                    (content, {**metadata, "topic": metadata.get("topic") or topic})
                    for content, metadata in items
                ]
            st.metric("Документов к импорту", len(items))
            st.dataframe(
                pd.DataFrame(
                    [{"content": content, "metadata": metadata} for content, metadata in items]
                ),
                width="stretch",
                height=320,
            )
            if st.button("Импортировать JSON", type="primary", width="stretch"):
                for content, metadata in items:
                    service.index_document(content, metadata)
                st.success(f"Импортировано документов: {len(items)}")
                st.rerun()
        except Exception as exc:
            st.error(str(exc))

    elif suffix == "csv":
        frame = pd.read_csv(uploaded)
        st.dataframe(frame.head(30), width="stretch")
        content_column = st.selectbox("Колонка с текстом", list(frame.columns))
        source_column_options = ["Не использовать"] + list(frame.columns)
        source_column = st.selectbox("Колонка source", source_column_options)
        topic_column_options = ["Не использовать"] + list(frame.columns)
        topic_column = st.selectbox("Колонка topic", topic_column_options)
        if st.button("Импортировать CSV", type="primary", width="stretch"):
            imported = 0
            for _, row in frame.iterrows():
                content = str(row.get(content_column, "")).strip()
                if not content:
                    continue
                metadata = {"source": source}
                if source_column != "Не использовать":
                    metadata["source"] = str(row.get(source_column) or metadata["source"])
                if topic:
                    metadata["topic"] = topic
                if topic_column != "Не использовать":
                    metadata["topic"] = str(row.get(topic_column) or metadata.get("topic", ""))
                service.index_document(content, metadata)
                imported += 1
            st.success(f"Импортировано строк: {imported}")
            st.rerun()


def render_analytics_tab(service: RagService, config: AppConfig, documents: list[Any], models: list[str]) -> None:
    st.markdown("### Аналитика базы знаний")
    stats = stats_frame(service)
    topics = topic_frame(documents)

    chart_col, topic_col = st.columns([1, 1])
    with chart_col:
        with st.container(border=True):
            st.markdown("#### Документы по источникам")
            if stats.empty:
                st.info("Пока нет документов.")
            else:
                st.bar_chart(stats.set_index("source"))
    with topic_col:
        with st.container(border=True):
            st.markdown("#### Документы по темам")
            if topics.empty:
                st.info("Пока нет тем.")
            else:
                st.bar_chart(topics.set_index("topic"))

    recent = documents_to_frame(documents[:10])
    st.markdown("### Последние документы")
    st.dataframe(recent, width="stretch", hide_index=True)

    st.markdown("### Состояние компонентов")
    status_col_1, status_col_2, status_col_3 = st.columns(3)
    status_col_1.metric("PostgreSQL", f"{config.db_host}:{config.db_port}")
    status_col_2.metric("LLM endpoint", config.lm_studio_url.replace("http://", ""))
    status_col_3.metric("Моделей LLM", len(models))
    if models:
        st.success("Локальная LLM отвечает")
        st.write(models)
    else:
        st.warning("Локальная LLM не вернула список моделей")


def render_settings_tab(service: RagService, config: AppConfig) -> None:
    st.markdown("### Настройки генерации и поиска")
    st.markdown(
        '<div class="note-panel"><span class="muted">Значения сохраняются в .env и применяются к текущему UI после сохранения.</span></div>',
        unsafe_allow_html=True,
    )

    with st.form("runtime_settings"):
        col_1, col_2 = st.columns(2)
        with col_1:
            llm_timeout = st.number_input(
                "LLM_TIMEOUT",
                min_value=5,
                max_value=600,
                value=int(config.llm_timeout),
                step=5,
            )
            llm_max_tokens = st.number_input(
                "LLM_MAX_TOKENS",
                min_value=32,
                max_value=4096,
                value=int(config.llm_max_tokens),
                step=32,
            )
        with col_2:
            llm_temperature = st.slider(
                "LLM_TEMPERATURE",
                min_value=0.0,
                max_value=1.5,
                value=float(config.llm_temperature),
                step=0.05,
            )
            default_top_k = st.slider(
                "DEFAULT_TOP_K",
                min_value=1,
                max_value=10,
                value=min(max(int(config.default_top_k), 1), 10),
            )

        saved = st.form_submit_button("Сохранить настройки", type="primary", width="stretch")

    if saved:
        updates = {
            "LLM_TIMEOUT": str(int(llm_timeout)),
            "LLM_MAX_TOKENS": str(int(llm_max_tokens)),
            "LLM_TEMPERATURE": f"{float(llm_temperature):.2f}".rstrip("0").rstrip("."),
            "DEFAULT_TOP_K": str(int(default_top_k)),
        }
        save_env_values(ENV_PATH, updates)
        service.llm.timeout = int(llm_timeout)
        service.llm.max_tokens = int(llm_max_tokens)
        service.llm.temperature = float(llm_temperature)
        st.success("Настройки сохранены")
        st.rerun()

    st.markdown("### Текущая конфигурация")
    st.json(
        {
            "DB": f"{config.db_host}:{config.db_port}/{config.db_name}",
            "EMBEDDING_MODEL": config.embedding_model,
            "VECTOR_DIM": config.vector_dimension,
            "LM_STUDIO_URL": config.lm_studio_url,
            "LLM_MODEL": config.llm_model or "auto",
            "LLM_TIMEOUT": config.llm_timeout,
            "LLM_MAX_TOKENS": config.llm_max_tokens,
            "LLM_TEMPERATURE": config.llm_temperature,
            "DEFAULT_TOP_K": config.default_top_k,
        }
    )

    action_col, clear_col = st.columns([1, 1])
    with action_col:
        if st.button("Добавить тестовые факты", width="stretch"):
            for content, metadata in SAMPLE_DOCUMENTS:
                service.index_document(content, metadata)
            st.success("Тестовые факты добавлены")
            st.rerun()
    with clear_col:
        confirm_clear = st.checkbox("Подтвердить очистку таблицы documents")
        if st.button("Очистить documents", disabled=not confirm_clear, width="stretch"):
            service.repository.truncate()
            st.warning("Таблица documents очищена")
            st.rerun()


inject_style()
config = get_config()

try:
    service = load_service(service_cache_key(config))
    sync_runtime_settings(service, config)
except Exception as exc:
    st.title("Lab 6-8 RAG Studio")
    st.error(str(exc))
    st.stop()

total_documents = service.repository.count_documents()
sources = service.repository.sources()
models = service.llm.list_models()
documents = service.repository.list_documents(limit=500)

render_header(config, total_documents, sources, models)

metric_1, metric_2, metric_3, metric_4 = st.columns(4)
metric_1.metric("Документы", total_documents)
metric_2.metric("Источники", len(sources))
metric_3.metric("top_k", config.default_top_k)
metric_4.metric("Температура", config.llm_temperature)

tab_rag, tab_kb, tab_import, tab_analytics, tab_settings = st.tabs(
    ["RAG-запрос", "База знаний", "Импорт", "Аналитика", "Настройки"]
)

with tab_rag:
    render_rag_tab(service, config, sources)

with tab_kb:
    render_knowledge_tab(service, sources)

with tab_import:
    render_import_tab(service)

with tab_analytics:
    render_analytics_tab(service, config, documents, models)

with tab_settings:
    render_settings_tab(service, config)

# Keep this last so generated Streamlit button styles cannot override the theme.
inject_style()
