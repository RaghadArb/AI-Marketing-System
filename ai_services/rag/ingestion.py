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

        # 1. Extract text
        text = self.loader.load(
            document.file.path
        )

        # 2. Split text
        chunks = self.chunker.split_text(
            text
        )

        # 3. Create embeddings and store
        for index, chunk in enumerate(chunks):

            embedding = self.embedding_service.create_embedding(
                chunk
            )

            self.vector_store.add_document(
                document_id=f"{document.id}_{index}",
                text=chunk,
                embedding=embedding,
                company_id=document.company.id
            )

        # Export once after all chunks
        self.vector_store.export_backup_files()

        return len(chunks)