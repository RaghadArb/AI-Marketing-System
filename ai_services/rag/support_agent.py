from .retriever import Retriever
from ai_services.clients.ollama_client import OllamaClient


class SupportAgent:

    def __init__(self):

        self.retriever = Retriever()
        self.llm = OllamaClient()


    def generate_answer(
        self,
        question,
        company_id
    ):

        documents = self.retriever.retrieve(
            question=question,
            company_id=company_id
        )


        context = "\n".join(
            documents["documents"][0]
        )


        prompt = f"""
You are a customer support assistant.

Answer the customer question using only the company information below.

Company information:
{context}

Customer question:
{question}

Answer:
"""


        response = self.llm.generate_response(
            prompt
        )

        return response