import requests

# takes the prompt and returns a response 

class OllamaClient:

    def __init__(self):

        self.url = "http://localhost:11434/api/generate"
        self.model = "llama3.2:1b"


    def generate_response(self, prompt):

        response = requests.post(
            self.url,
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 150,
                    "temperature": 0.3
                }
            }
        )
        response.raise_for_status()

        data = response.json()

        return data["response"]