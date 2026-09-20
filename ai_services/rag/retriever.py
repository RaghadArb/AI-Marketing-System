from .embeddings import EmbeddingService
from .vector_store import VectorStore
import re

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

        candidates = self.vector_store.search_with_evidence(
            embedding=query_embedding,
            company_id=company_id,
            n_results=max(10, int(n_results)),
        )
        return self._rerank(candidates, question, n_results)

    @staticmethod
    def _tokens(text):
        return {part for part in re.sub(r"[^\w\u0600-\u06ff]+", " ", str(text or "").lower()).split() if len(part) > 2}

    def _rerank(self, results, question, n_results):
        documents = (results or {}).get("documents") or [[]]
        texts = documents[0] if documents else []
        metadatas = ((results or {}).get("metadatas") or [[]])[0]
        distances = ((results or {}).get("distances") or [[]])[0]
        query_tokens = self._tokens(question)
        ranked = []
        for index, text in enumerate(texts):
            tokens = self._tokens(text)
            lexical = len(query_tokens & tokens) / max(1, len(query_tokens))
            distance = float(distances[index]) if index < len(distances) else 0.0
            semantic = 1.0 / (1.0 + max(0.0, distance))
            ranked.append((0.65 * semantic + 0.35 * lexical, index))
        ranked.sort(reverse=True)
        selected = [index for _, index in ranked[:max(1, int(n_results))]]
        output = {"documents": [[texts[i] for i in selected]], "metadatas": [[metadatas[i] for i in selected if i < len(metadatas)]], "distances": [[distances[i] for i in selected if i < len(distances)]]}
        ids = ((results or {}).get("ids") or [[]])[0]
        output["ids"] = [[ids[i] for i in selected if i < len(ids)]]
        return output

    def retrieve_evidence(
        self,
        question,
        company_id,
        n_results=3,
    ):
        from ai_services.analytics.knowledge_support import parse_query_results

        query_embedding = self.embedding_service.create_embedding(
            question
        )
        results = self.vector_store.search_with_evidence(
            embedding=query_embedding,
            company_id=company_id,
            n_results=n_results,
        )
        hits, has_distances = parse_query_results(results)
        return {
            "hits": hits,
            "has_distances": has_distances,
            "space": self.vector_store.distance_space(),
        }
