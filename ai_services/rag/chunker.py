import re


class TextChunker:
    """Split documents without cutting through words or natural boundaries."""

    _PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n+")
    _SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?؟؛])(?:[ \t]+|\n+)|\n+")

    def __init__(self, chunk_size=500, overlap=50):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if overlap < 0:
            raise ValueError("overlap cannot be negative")

        self.chunk_size = int(chunk_size)
        self.overlap = int(overlap)

    def split_text(self, text):
        text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        paragraphs = [
            paragraph.strip()
            for paragraph in self._PARAGRAPH_BOUNDARY.split(text)
            if paragraph.strip()
        ]
        if not paragraphs:
            return []

        chunks = []
        for paragraph in paragraphs:
            chunks.extend(self._split_paragraph(paragraph))

        chunks = self._merge_tiny_neighbors(chunks)
        return self._apply_boundary_overlap(chunks)

    def _split_paragraph(self, paragraph):
        if len(paragraph) <= self.chunk_size:
            return [paragraph]

        sentences = [
            sentence.strip()
            for sentence in self._SENTENCE_BOUNDARY.split(paragraph)
            if sentence.strip()
        ]
        units = []
        for sentence in sentences:
            if len(sentence) <= self.chunk_size:
                units.append(sentence)
            else:
                units.extend(self._split_at_words(sentence))

        return self._pack_units(units, " ")

    def _split_at_words(self, text):
        words = text.split()
        if not words:
            return []

        parts = []
        current = ""
        for word in words:
            candidate = self._join(current, word, " ")
            if current and len(candidate) > self.chunk_size:
                parts.append(current)
                current = word
            else:
                current = candidate

        if current:
            parts.append(current)

        return self._balance_word_tail(parts)

    def _pack_units(self, units, separator):
        chunks = []
        current = ""
        for unit in units:
            candidate = self._join(current, unit, separator)
            if current and len(candidate) > self.chunk_size:
                chunks.append(current)
                current = unit
            else:
                current = candidate

        if current:
            chunks.append(current)
        return self._merge_tiny_tail(chunks, separator)

    def _balance_word_tail(self, parts):
        if len(parts) < 2 or len(parts[-1]) >= self._minimum_tail_size():
            return parts

        previous_words = parts[-2].split()
        tail_words = parts[-1].split()
        while len(previous_words) > 1 and len(" ".join(tail_words)) < self._minimum_tail_size():
            candidate_tail = [previous_words[-1], *tail_words]
            if len(" ".join(candidate_tail)) > self.chunk_size:
                break
            tail_words = candidate_tail
            previous_words.pop()

        parts[-2] = " ".join(previous_words)
        parts[-1] = " ".join(tail_words)
        return parts

    def _merge_tiny_tail(self, chunks, separator):
        if len(chunks) < 2 or len(chunks[-1]) >= self._minimum_tail_size():
            return chunks

        merged = self._join(chunks[-2], chunks[-1], separator)
        if len(merged) <= self.chunk_size:
            return [*chunks[:-2], merged]
        return chunks

    def _merge_tiny_neighbors(self, chunks):
        merged = []
        index = 0
        minimum = self._minimum_tail_size()

        while index < len(chunks):
            current = chunks[index]
            while len(current) < minimum and index + 1 < len(chunks):
                candidate = self._join(current, chunks[index + 1], "\n\n")
                if len(candidate) > self.chunk_size:
                    break
                current = candidate
                index += 1

            if (
                len(current) < minimum
                and merged
                and len(self._join(merged[-1], current, "\n\n")) <= self.chunk_size
            ):
                merged[-1] = self._join(merged[-1], current, "\n\n")
            else:
                merged.append(current)
            index += 1

        return merged

    def _apply_boundary_overlap(self, chunks):
        if self.overlap <= 0 or len(chunks) < 2:
            return chunks

        overlapped = [chunks[0]]
        for chunk in chunks[1:]:
            boundary = self._last_boundary_unit(overlapped[-1])
            candidate = self._join(boundary, chunk, "\n\n") if boundary else chunk
            if boundary and len(boundary) <= self.overlap and len(candidate) <= self.chunk_size:
                overlapped.append(candidate)
            else:
                overlapped.append(chunk)
        return overlapped

    def _last_boundary_unit(self, chunk):
        paragraphs = [part.strip() for part in chunk.split("\n\n") if part.strip()]
        if len(paragraphs) > 1:
            return paragraphs[-1]

        sentences = [
            sentence.strip()
            for sentence in self._SENTENCE_BOUNDARY.split(chunk)
            if sentence.strip()
        ]
        if len(sentences) > 1:
            return sentences[-1]
        return ""

    def _minimum_tail_size(self):
        return min(100, max(20, self.chunk_size // 5))

    @staticmethod
    def _join(left, right, separator):
        if not left:
            return right
        if not right:
            return left
        return f"{left}{separator}{right}"
