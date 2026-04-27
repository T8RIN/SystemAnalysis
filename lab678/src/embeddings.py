from __future__ import annotations


class EmbeddingModel:
    def __init__(self, model_name: str, expected_dimension: int) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.expected_dimension = expected_dimension
        self._model = SentenceTransformer(model_name)
        if hasattr(self._model, "get_embedding_dimension"):
            self.dimension = int(self._model.get_embedding_dimension())
        else:
            self.dimension = int(self._model.get_sentence_embedding_dimension())
        if self.dimension != expected_dimension:
            message = (
                f"Модель {model_name} возвращает вектор размерности {self.dimension}, "
                f"а в .env указано VECTOR_DIM={expected_dimension}. "
                "Измените VECTOR_DIM или выберите другую модель эмбеддингов."
            )
            raise ValueError(message)

    def encode(self, text: str) -> list[float]:
        vector = self._model.encode(text, normalize_embeddings=True)
        return [float(value) for value in vector.tolist()]
