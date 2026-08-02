from ai_services.clients.ollama_client import OllamaClient


class ContentGenerator:


    def __init__(self):

        self.llm = OllamaClient()



    def generate_campaign_content(self, campaign, language):

        product_name = (
            campaign.product.product_name
            if campaign.product
            else "Unknown product"
        )


from ai_services.clients.ollama_client import OllamaClient


class ContentGenerator:


    def __init__(self):

        self.llm = OllamaClient()



    def generate_campaign_content(self, campaign, language):

        product_name = (
            campaign.product.product_name
            if campaign.product
            else "Unknown product"
        )


        prompt = f"""
        You are a professional marketing copywriter.

        Create 3 different marketing content suggestions for this campaign.

        Product:
        {product_name}

        Objective:
        {campaign.objective}

        Platform:
        {campaign.platform}


        Target language:
        {language}


        Rules:

        If language is English:
        - Write ONLY in English.
        - Do not use Arabic characters.
        - Hashtags must be English.

        If language is Arabic:
        - Write ONLY in Modern Standard Arabic.
        - Do not use English words.
        - Hashtags must be Arabic.


        Create exactly 3 suggestions.

        For each suggestion use this format:


        Suggestion 1

        Title:
        ...

        Caption:
        ...

        Hashtags:
        ...

        Short Description:
        ...


        Suggestion 2

        Title:
        ...

        Caption:
        ...

        Hashtags:
        ...

        Short Description:
        ...


        Suggestion 3

        Title:
        ...

        Caption:
        ...

        Hashtags:
        ...

        Short Description:
        ...


        Do not add explanations.
        Do not add introductions.
        Return only the marketing content.
        """


        response = self.llm.generate_response(
            prompt
        )


        return response


        response = self.llm.generate_response(
            prompt
        )


        return response