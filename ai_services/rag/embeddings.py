from sentence_transformers import SentenceTransformer


class EmbeddingService:

    _model = None
    MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self):

        if EmbeddingService._model is None:
            EmbeddingService._model = SentenceTransformer(
                EmbeddingService.MODEL_NAME
            )

        self.model = EmbeddingService._model


    def create_embedding(self, text):

        embedding = self.model.encode(
            text,
            convert_to_numpy=True
        )

        return embedding.tolist()
