import chromadb
import json
import os


class VectorStore:

    def __init__(self):

        self.client = chromadb.PersistentClient(
            path="chroma_db"
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
        company_id
    ):

        self.collection.add(
            ids=[str(document_id)],
            documents=[text],
            embeddings=[embedding],
            metadatas=[
                {
                    "company_id": company_id
                }
            ]
        )

    # Retrieve relevant documents
    def search(
        self,
        embedding,
        company_id,
        n_results=3
    ):

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where={
                "company_id": company_id
            }
        )

        return results

    # Export backup JSON files
    def export_backup_files(self):

        os.makedirs("ai_data", exist_ok=True)

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

        with open(
            "ai_data/knowledge_backup.json",
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                knowledge_data,
                f,
                ensure_ascii=False,
                indent=4
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

        vectors = embeddings.get("embeddings", [])
        documents = embeddings.get("documents", [])
        ids = embeddings.get("ids", [])

        for i in range(len(ids)):

            embedding_data.append(
                {
                    "id": ids[i],
                    "document": documents[i],
                    "embedding": vectors[i]
                }
            )

        with open(
            "ai_data/embeddings.json",
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                embedding_data,
                f,
                ensure_ascii=False,
                indent=4
            )