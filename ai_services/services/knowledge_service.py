from pathlib import Path

from pypdf import PdfReader
from docx import Document

from knowledge.models import KnowledgeDocument


class KnowledgeService:

    MAX_DOCUMENT_CHARS = 4000
    MAX_TOTAL_CHARS = 8000

    def get_company_context(self, company):

        documents = KnowledgeDocument.objects.filter(
            company=company
        ).order_by("-uploaded_at")

        context_parts = []
        total_length = 0

        for knowledge_document in documents:

            try:

                text = self._extract_text(
                    knowledge_document
                )

                if not text:
                    continue

                text = self._clean_text(text)

                if not text:
                    continue

                text = text[
                    :self.MAX_DOCUMENT_CHARS
                ]

                remaining = (
                    self.MAX_TOTAL_CHARS
                    - total_length
                )

                if remaining <= 0:
                    break

                text = text[:remaining]

                context_parts.append(
                    f"""
DOCUMENT TITLE:
{knowledge_document.title}

DOCUMENT DESCRIPTION:
{knowledge_document.description or "No description"}

DOCUMENT CONTENT:
{text}
                    """.strip()
                )

                total_length += len(text)

            except Exception as e:

                print(
                    f"Knowledge document skipped "
                    f"({knowledge_document.id}): {e}"
                )

                continue

        if not context_parts:

            return ""

        return "\n\n---\n\n".join(
            context_parts
        )


    def _extract_text(
        self,
        knowledge_document
    ):

        if not knowledge_document.file:
            return ""

        file_path = Path(
            knowledge_document.file.path
        )

        if not file_path.exists():
            return ""

        extension = (
            file_path.suffix
            .lower()
        )

        if extension == ".txt":

            return self._extract_txt(
                file_path
            )

        if extension == ".pdf":

            return self._extract_pdf(
                file_path
            )

        if extension == ".docx":

            return self._extract_docx(
                file_path
            )

        return ""


    def _extract_txt(
        self,
        file_path
    ):

        return file_path.read_text(
            encoding="utf-8",
            errors="ignore"
        )


    def _extract_pdf(
        self,
        file_path
    ):

        reader = PdfReader(
            str(file_path)
        )

        pages = []

        for page in reader.pages:

            text = page.extract_text()

            if text:
                pages.append(text)

        return "\n".join(pages)


    def _extract_docx(
        self,
        file_path
    ):

        document = Document(
            str(file_path)
        )

        paragraphs = [
            paragraph.text
            for paragraph
            in document.paragraphs
            if paragraph.text.strip()
        ]

        return "\n".join(
            paragraphs
        )


    def _clean_text(
        self,
        text
    ):

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        return "\n".join(lines)