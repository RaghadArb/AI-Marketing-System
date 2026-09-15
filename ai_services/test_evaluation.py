from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from ai_services.evaluation.chatbot import (
    evaluate_chatbot_case,
    run_chatbot_evaluation,
)
from ai_services.evaluation.content import (
    evaluate_content_case,
    split_suggestions,
)
from ai_services.evaluation.grader import (
    GradingUnavailable,
    extract_json_object,
)
from ai_services.evaluation.io import load_json, write_csv, write_json
from ai_services.evaluation.metrics import (
    CORRECTNESS_THRESHOLD,
    chatbot_summary,
    content_quality_from_scores,
    content_summary,
    is_correct,
    retrieval_hit,
)


class EvaluationMetricTests(SimpleTestCase):
    def test_correctness_threshold(self):
        self.assertTrue(is_correct(0.8))
        self.assertTrue(is_correct(1))
        self.assertFalse(is_correct(0.79))
        self.assertIsNone(is_correct(None))
        self.assertEqual(CORRECTNESS_THRESHOLD, 0.8)

    def test_accuracy_ignores_missing_scores(self):
        summary = chatbot_summary(
            [
                {"status": "evaluated", "correctness_score": 0.9, "retrieval_hit": True, "hallucinated": False, "faithfulness_score": 1, "relevance_score": 1},
                {"status": "evaluated", "correctness_score": None, "retrieval_hit": True, "grading_error": "bad json"},
                {"status": "skipped"},
            ]
        )
        self.assertEqual(summary["total_test_cases"], 3)
        self.assertEqual(summary["evaluated_cases"], 2)
        self.assertEqual(summary["answer_accuracy_percent"], 100.0)
        self.assertEqual(summary["correctness_valid_n"], 1)

    def test_empty_dataset_metrics_are_null_not_zero(self):
        summary = chatbot_summary([])
        self.assertEqual(summary["total_test_cases"], 0)
        self.assertIsNone(summary["answer_accuracy_percent"])
        self.assertIsNone(summary["average_correctness_score"])
        self.assertIsNone(summary["retrieval_hit_rate_percent"])
        self.assertIsNone(summary["hallucination_rate_percent"])

    def test_retrieval_hit_and_missing_context(self):
        self.assertTrue(
            retrieval_hit(
                "Hours are 9am to 5pm every weekday.",
                ["hours.pdf"],
                expected_source="hours.pdf",
            )
        )
        self.assertFalse(
            retrieval_hit(
                "",
                [],
                expected_knowledge_text="9am to 5pm",
            )
        )
        self.assertIsNone(retrieval_hit("", [], "", "", ""))

    def test_content_quality_formula(self):
        quality = content_quality_from_scores(
            {
                "campaign_relevance": 5,
                "factual_consistency": 5,
                "platform_appropriateness": 5,
                "language_quality": 5,
                "cta_quality": 5,
            }
        )
        self.assertEqual(quality["total_score"], 25)
        self.assertEqual(quality["quality_percentage"], 100.0)
        self.assertIsNone(
            content_quality_from_scores(
                {
                    "campaign_relevance": 5,
                    "factual_consistency": None,
                    "platform_appropriateness": 5,
                    "language_quality": 5,
                    "cta_quality": 5,
                }
            )
        )

    def test_content_summary_average(self):
        summary = content_summary(
            [
                {"status": "evaluated", "quality_percentage": 80},
                {"status": "evaluated", "quality_percentage": 60},
                {"status": "failed"},
            ]
        )
        self.assertEqual(summary["metric_name"], "Marketing Content Quality Score")
        self.assertEqual(summary["overall_content_quality"], 70.0)


class GraderParsingTests(SimpleTestCase):
    def test_malformed_grader_json_raises(self):
        with self.assertRaises(GradingUnavailable):
            extract_json_object("the answer is good")

    def test_embedded_json_is_parsed(self):
        payload = extract_json_object('Note: {"score": 0.5, "ok": true}')
        self.assertEqual(payload["score"], 0.5)


class ChatbotEvaluationFlowTests(SimpleTestCase):
    def test_skips_template_company_id(self):
        record = evaluate_chatbot_case(
            {
                "id": "t1",
                "company_id": "REPLACE_WITH_COMPANY_ID",
                "question": "Hours?",
                "expected_answer": "9am",
            },
            agent=MagicMock(),
        )
        self.assertEqual(record["status"], "skipped")
        self.assertIsNone(record["correctness_score"])

    def test_missing_context_is_a_retrieval_miss(self):
        agent = MagicMock()
        agent.generate_answer.return_value = "We deliver nationwide."
        agent.last_documents = {"documents": [[]], "metadatas": [[]], "ids": [[]]}
        agent.last_context = ""
        llm = MagicMock()
        llm.generate.return_value = (
            '{"correctness": {"score": 0.2, "reason": "wrong"},'
            ' "faithfulness": {"score": 0.0, "reason": "no context"},'
            ' "relevance": {"score": 0.8, "reason": "on topic"},'
            ' "unsupported_important_claims": true}'
        )
        record = evaluate_chatbot_case(
            {
                "id": "t2",
                "company_id": 1,
                "question": "Do you deliver?",
                "expected_answer": "Local delivery only",
                "expected_knowledge_text": "local delivery",
            },
            agent=agent,
            grader_llm=llm,
        )
        self.assertEqual(record["status"], "evaluated")
        self.assertFalse(record["retrieval_hit"])
        self.assertTrue(record["hallucinated"])
        self.assertEqual(record["correctness_score"], 0.2)

    def test_malformed_grade_does_not_become_zero(self):
        agent = MagicMock()
        agent.generate_answer.return_value = "Hello"
        agent.last_documents = {
            "documents": [["Hello policy"]],
            "metadatas": [[{"source": "faq"}]],
            "ids": [["1"]],
        }
        agent.last_context = "Hello policy"
        llm = MagicMock()
        llm.generate.return_value = "I think this is fine"
        record = evaluate_chatbot_case(
            {
                "id": "t3",
                "company_id": 1,
                "question": "Hi",
                "expected_answer": "Hello",
            },
            agent=agent,
            grader_llm=llm,
        )
        self.assertEqual(record["status"], "evaluated")
        self.assertIsNone(record["correctness_score"])
        self.assertIsNone(record["is_correct"])
        self.assertTrue(record["grading_error"])

    def test_empty_dataset(self):
        records, summary = run_chatbot_evaluation([], agent=MagicMock())
        self.assertEqual(records, [])
        self.assertIsNone(summary["answer_accuracy_percent"])


class ContentEvaluationFlowTests(SimpleTestCase):
    def test_skips_template_campaign_id(self):
        records = evaluate_content_case(
            {"id": "c1", "campaign_id": "REPLACE_WITH_CAMPAIGN_ID"},
            generator=MagicMock(),
        )
        self.assertEqual(records[0]["status"], "skipped")

    def test_split_suggestions(self):
        text = (
            "Suggestion 1\nTitle: A\nCaption: one\nCall to Action: go\n"
            "Suggestion 2\nTitle: B\nCaption: two\nCall to Action: visit"
        )
        parts = split_suggestions(text)
        self.assertEqual(len(parts), 2)

    def test_content_grades_each_suggestion(self):
        campaign = SimpleNamespace(
            id=7,
            objective="Increase sales",
            platform="Instagram",
            company=SimpleNamespace(company_name="Cafe"),
            product=SimpleNamespace(product_name="Latte"),
        )
        generator = MagicMock()
        generator.generate_campaign_content.return_value = {
            "content": (
                "Suggestion 1\nTitle: One\nCaption: Hello\nCall to Action: Visit\n"
                "Suggestion 2\nTitle: Two\nCaption: Hi\nCall to Action: Shop"
            ),
            "validation": {"is_valid": True, "errors": []},
        }
        llm = MagicMock()
        llm.generate.return_value = (
            '{"campaign_relevance": {"score": 4, "reason": "on brief"},'
            ' "factual_consistency": {"score": 5, "reason": "no invented facts"},'
            ' "platform_appropriateness": {"score": 4, "reason": "instagram"},'
            ' "language_quality": {"score": 4, "reason": "clear"},'
            ' "cta_quality": {"score": 3, "reason": "generic"}}'
        )
        with patch(
            "ai_services.evaluation.content._load_campaign",
            return_value=campaign,
        ):
            records = evaluate_content_case(
                {"id": "c2", "campaign_id": 7, "creative_brief": {}},
                generator=generator,
                grader_llm=llm,
            )
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["total_score"], 20)
        self.assertEqual(records[0]["quality_percentage"], 80.0)
        self.assertEqual(records[0]["status"], "evaluated")

    def test_malformed_content_grade_is_unavailable(self):
        campaign = SimpleNamespace(
            id=7,
            objective="Sales",
            platform="Instagram",
            company=SimpleNamespace(company_name="Cafe"),
            product=None,
        )
        generator = MagicMock()
        generator.generate_campaign_content.return_value = {
            "content": "Suggestion 1\nTitle: One\nCaption: Hello\nCall to Action: Visit",
            "validation": {},
        }
        llm = MagicMock()
        llm.generate.return_value = "excellent work"
        with patch(
            "ai_services.evaluation.content._load_campaign",
            return_value=campaign,
        ):
            records = evaluate_content_case(
                {"id": "c3", "campaign_id": 7},
                generator,
                grader_llm=llm,
            )
        self.assertIsNone(records[0]["quality_percentage"])
        self.assertTrue(records[0]["grading_error"])


class EvaluationIoTests(SimpleTestCase):
    def test_json_and_csv_round_trip(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            rows = [
                {
                    "id": "1",
                    "status": "evaluated",
                    "correctness_score": 0.9,
                    "error": None,
                }
            ]
            json_path = write_json(folder / "out.json", rows)
            csv_path = write_csv(
                folder / "out.csv",
                rows,
                ["id", "status", "correctness_score", "error"],
            )
            loaded = load_json(json_path)
            self.assertEqual(loaded[0]["correctness_score"], 0.9)
            csv_text = csv_path.read_text(encoding="utf-8")
            self.assertIn("correctness_score", csv_text)
            self.assertIn("0.9", csv_text)

    def test_template_datasets_are_not_results(self):
        from ai_services.evaluation.io import CHATBOT_TEMPLATE, CONTENT_TEMPLATE

        chatbot = load_json(CHATBOT_TEMPLATE)
        content = load_json(CONTENT_TEMPLATE)
        self.assertTrue(chatbot)
        self.assertEqual(chatbot[0]["company_id"], "REPLACE_WITH_COMPANY_ID")
        self.assertEqual(content[0]["campaign_id"], "REPLACE_WITH_CAMPAIGN_ID")
