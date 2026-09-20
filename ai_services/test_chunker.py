from django.test import SimpleTestCase

from ai_services.rag.chunker import TextChunker


class TextChunkerTests(SimpleTestCase):
    def test_preserves_arabic_paragraphs(self):
        first = "متجر الندى متجر إلكتروني سعودي للعناية بالبشرة."
        second = "لا يقدم المتجر تشخيصاً طبياً أو علاجاً جلدياً."
        chunks = TextChunker(chunk_size=70, overlap=0).split_text(
            f"{first}\n\n{second}"
        )

        self.assertEqual(chunks, [first, second])

    def test_never_splits_words(self):
        text = " ".join(
            [
                "العناية",
                "التجميلية",
                "بالبشرة",
                "مباشرة",
                "للمستهلكين",
                "داخل",
                "المملكة",
            ]
        )
        chunks = TextChunker(chunk_size=25, overlap=0).split_text(text)

        self.assertEqual(
            " ".join(" ".join(chunks).split()),
            " ".join(text.split()),
        )
        self.assertTrue(all(word in text.split() for chunk in chunks for word in chunk.split()))

    def test_splits_long_paragraph_at_sentence_boundaries(self):
        sentences = [
            "الجملة الأولى تشرح معلومات الشركة.",
            "الجملة الثانية توضح نطاق الخدمة.",
            "الجملة الثالثة تعرض وسائل التواصل.",
        ]
        chunks = TextChunker(chunk_size=75, overlap=0).split_text(
            " ".join(sentences)
        )

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 75 for chunk in chunks))
        for sentence in sentences:
            self.assertTrue(any(sentence in chunk for chunk in chunks))

    def test_balances_a_tiny_word_tail(self):
        text = " ".join(f"كلمة{i}" for i in range(1, 16))
        chunker = TextChunker(chunk_size=50, overlap=0)
        chunks = chunker.split_text(text)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 50 for chunk in chunks))
        self.assertGreaterEqual(len(chunks[-1]), chunker._minimum_tail_size())
        self.assertEqual(" ".join(chunks).split(), text.split())

    def test_respects_maximum_size_for_normal_words(self):
        text = " ".join(["منتج" for _ in range(80)])
        chunks = TextChunker(chunk_size=80, overlap=20).split_text(text)

        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk) <= 80 for chunk in chunks))
