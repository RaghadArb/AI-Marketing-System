from .embeddings import EmbeddingService
from .vector_store import VectorStore

# retrievers job is to call the embeddings service to convert the text into vector and
# then calls vector store to retrieve the related documents and store the embedding in the chromadb
class Retriever:

    def __init__(self):

        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore()

    def retrieve(
        self,
        question,
        company_id,
        n_results=3
    ):

        query_embedding = self.embedding_service.create_embedding(
            question
        )

        results = self.vector_store.search(
            embedding=query_embedding,
            company_id=company_id,
            n_results=n_results
        )

        return results