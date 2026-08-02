from sentence_transformers import SentenceTransformer


class EmbeddingService:

    _model = None

    def __init__(self):

        if EmbeddingService._model is None:
            EmbeddingService._model = SentenceTransformer(
                "all-MiniLM-L6-v2"
            )

        self.model = EmbeddingService._model


    def create_embedding(self, text):

        embedding = self.model.encode(
            text,
            convert_to_numpy=True
        )

        return embedding.tolist()