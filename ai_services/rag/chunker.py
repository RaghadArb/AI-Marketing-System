# split the text extracted from the documents into chunks to send to the model
# so that i wouldnt search inside the whole documents i would be searching inside chunks 

class TextChunker:


    def __init__(
        self,
        chunk_size=500,
        overlap=50
    ):
        # overlapping so that the context wouldnt be lost between chunks 
        # for example: 
        """
        Our company sells coffee, burgers, desserts...
        
        Chunk 1:
        Our company sells coffee...

        Chunk 2:
        coffee, burgers, desserts...

        Chunk 3:
        desserts, prices, opening hours...
        """
        
        self.chunk_size = chunk_size
        self.overlap = overlap



    def split_text(
        self,
        text
    ):

        chunks = []

        start = 0

        text_length = len(text)


        while start < text_length:

            end = start + self.chunk_size

            chunk = text[start:end]

            chunks.append(chunk)


            start = end - self.overlap


        return chunks