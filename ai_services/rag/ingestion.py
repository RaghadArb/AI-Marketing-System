from .document_loader import DocumentLoader
from .chunker import TextChunker
from .embeddings import EmbeddingService
from .vector_store import VectorStore

#connects all the process of loading document -> extracting text -> splitting into chunks -> creating embeddings -> storing in chromaDB

class DocumentIngestionService:


    def __init__(self):

        self.loader = DocumentLoader()
        self.chunker = TextChunker()
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore()



    def process_document(self, document):

        self.vector_store.delete_document_chunks(
            document.id
        )

        # 1. Extract text
        text = self.loader.load(
            document.file.path
        )

        # 2. Split text
        chunks = self.chunker.split_text(
            text
        )

        if not chunks:
            return 0

        # 3. Create embeddings and store
        for index, chunk in enumerate(chunks):

            embedding = self.embedding_service.create_embedding(
                chunk
            )

            source_name = ""
            if document.file:
                source_name = str(document.file.name).replace("\\", "/").rsplit("/", 1)[-1]

            self.vector_store.add_document(
                document_id=f"{document.id}_{index}",
                text=chunk,
                embedding=embedding,
                company_id=document.company.id,
                metadata={
                    "knowledge_document_id": int(document.id),
                    "source": source_name or document.title,
                },
            )

        # Export once after all chunks
        self.vector_store.export_backup_files()

        return len(chunks)

    def ingest_company_profile(self, company):
        parts = [
            f"Company name: {company.company_name}",
            f"Industry: {company.industry or 'Not provided'}",
            f"Description: {company.description or 'Not provided'}",
        ]

        if company.website:
            parts.append(f"Website: {company.website}")

        text = "\n".join(parts).strip()

        if not text:
            return 0

        embedding = self.embedding_service.create_embedding(text)
        self.vector_store.add_document(
            document_id=f"company_profile_{company.id}",
            text=text,
            embedding=embedding,
            company_id=company.id,
        )
        return 1

    def ingest_company_documents(self, company):
        from knowledge.models import KnowledgeDocument

        indexed = 0

        try:
            indexed += self.ingest_company_profile(company)
        except Exception:
            pass

        documents = KnowledgeDocument.objects.filter(
            company=company
        )

        for document in documents:
            if not document.file:
                continue

            try:
                indexed += self.process_document(document)
            except Exception:
                continue

        try:
            self.vector_store.export_backup_files()
        except Exception:
            pass

        return indexed