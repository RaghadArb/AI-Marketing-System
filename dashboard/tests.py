from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from ai_services.services.campaign_advisor import CampaignAdvisor
from dashboard.presentation import (
    campaign_progress_percent,
    parse_suggestion_display,
)


class CampaignProgressTests(SimpleTestCase):

    def test_missing_dates_return_none(self):
        campaign = SimpleNamespace(start_date=None, end_date=None)
        self.assertIsNone(campaign_progress_percent(campaign))

    def test_future_campaign_is_zero(self):
        campaign = SimpleNamespace(
            start_date=date.today() + timedelta(days=5),
            end_date=date.today() + timedelta(days=15),
        )
        self.assertEqual(campaign_progress_percent(campaign), 0)

    def test_ended_campaign_is_hundred(self):
        campaign = SimpleNamespace(
            start_date=date.today() - timedelta(days=20),
            end_date=date.today() - timedelta(days=1),
        )
        self.assertEqual(campaign_progress_percent(campaign), 100)


class SuggestionDisplayTests(SimpleTestCase):

    def test_parses_structured_sections(self):
        text = (
            "Title: Glow Serum\n"
            "Caption: Brighten your morning routine.\n"
            "Call to Action: Shop the serum today.\n"
            "Hashtags: #skincare #glow"
        )
        display = parse_suggestion_display(text)
        self.assertTrue(display["parsed"])
        self.assertEqual(display["caption"], "Brighten your morning routine.")
        self.assertIn("Shop the serum", display["cta"])

    def test_falls_back_when_unstructured(self):
        display = parse_suggestion_display("Just a plain caption.")
        self.assertFalse(display["parsed"])
        self.assertEqual(display["raw"], "Just a plain caption.")


class CampaignAdvisorTests(SimpleTestCase):

    def test_insufficient_data_skips_llm(self):
        llm = MagicMock()
        advisor = CampaignAdvisor(llm=llm)
        campaign = SimpleNamespace(
            campaign_name="Demo",
            platform="Instagram",
            status="Active",
            budget=None,
        )
        result = advisor.generate(campaign, {})
        self.assertTrue(result["insufficient_data"])
        llm.generate.assert_not_called()

    def test_parses_json_from_mocked_llm(self):
        llm = MagicMock()
        llm.generate.return_value = """
        {
          "performance_insight": "CTR is healthy for the recorded views.",
          "strengths": ["Strong click-through"],
          "weaknesses": ["Engagement could improve"],
          "recommended_actions": ["Test a clearer CTA", "Review creative"]
        }
        """
        advisor = CampaignAdvisor(llm=llm)
        campaign = SimpleNamespace(
            campaign_name="Demo",
            platform="Instagram",
            status="Active",
            budget="500.00",
        )
        result = advisor.generate(
            campaign,
            {"total_views": 1000, "total_clicks": 80, "average_ctr": 8.0},
        )
        self.assertEqual(
            result["performance_insight"],
            "CTR is healthy for the recorded views.",
        )
        self.assertEqual(len(result["recommended_actions"]), 2)
        llm.generate.assert_called_once()
