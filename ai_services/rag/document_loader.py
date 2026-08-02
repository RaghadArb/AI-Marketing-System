import os
from pypdf import PdfReader
from docx import Document

# to read the files stored in the knowledge base of the company 

class DocumentLoader:


    def load(self, file_path):

        extension = os.path.splitext(file_path)[1].lower()


        if extension == ".pdf":
            return self._load_pdf(file_path)


        elif extension == ".docx":
            return self._load_docx(file_path)


        elif extension == ".txt":
            return self._load_txt(file_path)


        else:
            raise ValueError(
                "Unsupported document type"
            )


    def _load_pdf(self, file_path):

        reader = PdfReader(file_path)

        text = ""

        for page in reader.pages:
            text += page.extract_text() or ""

        return text



    def _load_docx(self, file_path):

        doc = Document(file_path)

        return "\n".join(
            paragraph.text
            for paragraph in doc.paragraphs
        )



    def _load_txt(self, file_path):

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as file:

            return file.read()