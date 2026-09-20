import chromadb
import json
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
CHROMA_PATH = BASE_DIR / "chroma_db"
AI_DATA_PATH = BASE_DIR / "ai_data"


def _json_ready(value):
    """Convert Chroma/NumPy return values to plain JSON-compatible data."""
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _write_json_atomic(path, data):
    temporary_path = f"{path}.tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(
                _json_ready(data),
                file,
                ensure_ascii=False,
                indent=4,
            )
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)


class VectorStore:

    def __init__(self):

        self.client = chromadb.PersistentClient(
            path=str(CHROMA_PATH)
        )

        self.collection = self.client.get_or_create_collection(
            name="company_documents"
        )

    # Add embeddings to ChromaDB
    def add_document(
        self,
        document_id,
        text,
        embedding,
        company_id,
        metadata=None,
    ):

        item_metadata = {
            "company_id": int(company_id)
        }

        if metadata:
            item_metadata.update(metadata)

        self.collection.add(
            ids=[str(document_id)],
            documents=[text],
            embeddings=[embedding],
            metadatas=[item_metadata]
        )

    # Retrieve relevant documents
    def search(
        self,
        embedding,
        company_id,
        n_results=3
    ):

        return self._query(
            embedding=embedding,
            company_id=company_id,
            n_results=n_results,
            include=None,
        )

    def search_with_evidence(
        self,
        embedding,
        company_id,
        n_results=3,
    ):
        return self._query(
            embedding=embedding,
            company_id=company_id,
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

    def distance_space(self):
        from ai_services.analytics.knowledge_support import collection_space

        return collection_space(self)

    def _query(self, embedding, company_id, n_results=3, include=None):
        where_filter = {
            "$or": [
                {"company_id": int(company_id)},
                {"company_id": str(company_id)},
            ]
        }
        kwargs = {
            "query_embeddings": [embedding],
            "n_results": max(1, int(n_results)),
            "where": where_filter,
        }
        if include:
            kwargs["include"] = include

        try:
            return self.collection.query(**kwargs)
        except Exception:
            fallback = {
                "query_embeddings": [embedding],
                "n_results": max(1, int(n_results)),
                "where": {"company_id": int(company_id)},
            }
            if include:
                fallback["include"] = include
            try:
                return self.collection.query(**fallback)
            except Exception:
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    def company_has_chunks(self, company_id):
        for where_filter in (
            {"company_id": int(company_id)},
            {"company_id": str(company_id)},
        ):
            try:
                existing = self.collection.get(
                    where=where_filter,
                    limit=1,
                    include=[],
                )
                if existing.get("ids"):
                    return True
            except Exception:
                continue

        return False

    def document_chunk_counts(self, document_ids):
        counts = {
            int(document_id): 0
            for document_id in document_ids
        }

        if not counts:
            return counts

        try:
            existing = self.collection.get(
                include=["metadatas"]
            )
        except Exception:
            return counts

        ids = existing.get("ids") or []
        metadatas = existing.get("metadatas") or []

        for index, item_id in enumerate(ids):
            matched = None
            if index < len(metadatas) and isinstance(metadatas[index], dict):
                raw = metadatas[index].get("knowledge_document_id")
                try:
                    matched = int(raw)
                except (TypeError, ValueError):
                    matched = None

            if matched is None:
                text_id = str(item_id)
                for document_id in counts:
                    if text_id.startswith(f"{document_id}_"):
                        matched = document_id
                        break

            if matched in counts:
                counts[matched] += 1

        return counts

    def delete_document_chunks(self, knowledge_document_id):
        prefix = f"{knowledge_document_id}_"
        existing = self.collection.get(include=[])
        ids = [
            item_id
            for item_id in (existing.get("ids") or [])
            if str(item_id).startswith(prefix)
        ]

        if ids:
            self.collection.delete(ids=ids)

        return len(ids)

    # Export backup JSON files
    def export_backup_files(self):

        os.makedirs(AI_DATA_PATH, exist_ok=True)

        # -----------------------------
        # Knowledge Backup
        # -----------------------------

        knowledge = self.collection.get(
            include=[
                "documents",
                "metadatas"
            ]
        )

        knowledge_data = []

        documents = knowledge.get("documents", [])
        metadatas = knowledge.get("metadatas", [])
        ids = knowledge.get("ids", [])

        for i in range(len(ids)):

            knowledge_data.append(
                {
                    "id": ids[i],
                    "document": documents[i],
                    "metadata": metadatas[i]
                }
            )

        _write_json_atomic(
            AI_DATA_PATH / "knowledge_backup.json",
            knowledge_data,
        )

        # -----------------------------
        # Embeddings Backup
        # -----------------------------

        embeddings = self.collection.get(
            include=[
                "documents",
                "embeddings"
            ]
        )

        embedding_data = []

        vectors = embeddings.get("embeddings")
        if vectors is None:
            vectors = []
        documents = embeddings.get("documents", [])
        ids = embeddings.get("ids", [])

        for i in range(len(ids)):

            embedding_data.append(
                {
                    "id": ids[i],
                    "document": documents[i],
                    "embedding": _json_ready(vectors[i])
                }
            )

        _write_json_atomic(
            AI_DATA_PATH / "embeddings.json",
            embedding_data,
        )
