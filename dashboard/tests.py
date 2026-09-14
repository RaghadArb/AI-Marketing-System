from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import Client, SimpleTestCase, TestCase

from ai_services.analytics.metrics import calculate_aggregate_ctr
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


class AggregateCtrTests(SimpleTestCase):

    def test_aggregate_ctr_does_not_average_row_percentages(self):
        self.assertEqual(calculate_aggregate_ctr(110, 10100), 1.09)
        self.assertNotEqual(calculate_aggregate_ctr(110, 10100), 5.5)

    def test_zero_impressions_returns_none(self):
        self.assertIsNone(calculate_aggregate_ctr(10, 0))
        self.assertIsNone(calculate_aggregate_ctr(10, None))


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
        self.assertEqual(result["overall_evaluation"], "Strong")
        self.assertTrue(result["evaluation_basis"])
        llm.generate.assert_called_once()

    def test_strategy_context_does_not_invent_metrics(self):
        llm = MagicMock()
        llm.generate.return_value = """
        {
          "performance_insight": "Views are present; no conversion data was supplied.",
          "strengths": ["Reach"],
          "weaknesses": ["No conversion metric recorded"],
          "recommended_actions": ["Keep measuring clicks"]
        }
        """
        advisor = CampaignAdvisor(llm=llm)
        campaign = SimpleNamespace(
            campaign_name="Demo",
            platform="Instagram",
            status="Active",
            budget="500.00",
            objective="Grow iced coffee sales",
        )
        result = advisor.generate(
            campaign,
            {"total_views": 200, "total_clicks": 4, "average_ctr": 2.0},
            strategy_context={
                "campaign_objective": "Grow iced coffee sales",
                "planned_kpi_themes": ["Awareness"],
            },
        )
        prompt = llm.generate.call_args.kwargs["prompt"]
        self.assertIn("Grow iced coffee sales", prompt)
        self.assertIn("Do not invent expected KPI numbers", prompt)
        self.assertEqual(result["overall_evaluation"], "Strong")
        self.assertNotIn("74/100", result["overall_evaluation"])


class MarketingStrategyAgentTests(SimpleTestCase):

    def test_parses_valid_json(self):
        from ai_services.services.marketing_strategy_agent import (
            MarketingStrategyAgent,
        )

        llm = MagicMock()
        llm.generate.return_value = """
        {
          "campaign_objective": "Increase iced coffee sales.",
          "target_audience": "University students 18-25",
          "recommended_platform": "Instagram",
          "strategy_summary": "Affordable summer campaign.",
          "content_strategy": ["Reels", "Campus stories"],
          "creative_direction": "Bright summer tones",
          "budget_strategy": "Most spend on Instagram ads",
          "recommended_kpis": ["Reach", "CTR"],
          "messaging_angle": "Affordable refreshment",
          "call_to_action_strategy": "Visit this week",
          "reasoning": "Fits the audience and budget."
        }
        """
        agent = MarketingStrategyAgent(llm=llm)
        result = agent.generate({"marketing_goal": "Sell more iced coffee"})
        self.assertEqual(result["recommended_platform"], "Instagram")
        self.assertEqual(len(result["content_strategy"]), 2)
        llm.generate.assert_called_once()

    def test_malformed_json_raises(self):
        from ai_services.services.marketing_strategy_agent import (
            MarketingStrategyAgent,
            StrategyGenerationError,
        )

        llm = MagicMock()
        llm.generate.return_value = "Sorry, here is a plan without JSON."
        agent = MarketingStrategyAgent(llm=llm)
        with self.assertRaises(StrategyGenerationError):
            agent.generate({"marketing_goal": "Sell more"})


class ContentGeneratorContractTests(SimpleTestCase):

    def test_still_requests_exactly_three_suggestions(self):
        from ai_services.services import content_generator as module

        source = open(module.__file__, encoding="utf-8").read()
        self.assertIn("exactly THREE", source)
        self.assertIn("Suggestion 3", source)


SAMPLE_STRATEGY = {
    "campaign_objective": "Increase iced coffee sales during September.",
    "target_audience": "University students aged 18-25.",
    "recommended_platform": "Instagram",
    "strategy_summary": "Promote affordability and a summer campus mood.",
    "content_strategy": [
        "Short Reels of iced coffee on campus",
        "Student testimonials",
        "Limited September offer creative",
    ],
    "creative_direction": "Bright, warm, affordable summer atmosphere",
    "budget_strategy": "Concentrate spend on Instagram during term weeks",
    "recommended_kpis": ["Reach", "CTR", "Profile visits"],
    "messaging_angle": "Refreshing coffee that fits a student budget",
    "call_to_action_strategy": "Visit this week and try the iced coffee",
    "reasoning": "The audience is on Instagram and the budget is modest.",
}


class StrategyPlannerViewTests(TestCase):

    def setUp(self):
        from django.contrib.auth.models import User

        from campaign.models import Campaign
        from companies.models import Company
        from products.models import Product

        self.Campaign = Campaign
        self.user = User.objects.create_user("specialist", password="pass123")
        self.other = User.objects.create_user("outsider", password="pass123")
        self.company = Company.objects.create(
            owner=self.user,
            company_name="Campus Cafe",
            industry="Restaurant",
        )
        self.other_company = Company.objects.create(
            owner=self.other,
            company_name="Other Cafe",
            industry="Restaurant",
        )
        self.product = Product.objects.create(
            company=self.company,
            product_name="Iced Coffee",
            category="Drinks",
            description="Cold brew with ice",
            price="4.50",
        )
        Product.objects.create(
            company=self.other_company,
            product_name="Secret Blend",
            category="Drinks",
            price="5.00",
        )
        self.client.force_login(self.user)

    def test_requires_marketing_specialist(self):
        anon = Client()
        response = anon.get("/dashboard/strategy-planner/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_company_dropdown_is_owner_scoped(self):
        response = self.client.get("/dashboard/strategy-planner/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Campus Cafe", body)
        self.assertNotIn("Other Cafe", body)
        self.assertIn("Iced Coffee", body)
        self.assertNotIn("Secret Blend", body)

    def test_get_does_not_call_ai(self):
        with patch("dashboard.views.MarketingStrategyAgent") as mocked:
            response = self.client.get("/dashboard/strategy-planner/")
        self.assertEqual(response.status_code, 200)
        mocked.assert_not_called()

    def _brief(self, **overrides):
        payload = {
            "action": "generate_strategy",
            "company_id": str(self.company.id),
            "product_id": str(self.product.id),
            "marketing_goal": "Increase sales of iced coffee in September.",
            "target_audience": "University students aged 18-25.",
            "budget": "1000",
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
            "preferred_platform": "Instagram",
            "additional_information": "Focus on affordability.",
        }
        payload.update(overrides)
        return payload

    def test_generate_uses_mocked_agent_and_does_not_create_campaign(self):
        mocked_agent = MagicMock()
        mocked_agent.generate.return_value = dict(SAMPLE_STRATEGY)
        with patch(
            "dashboard.views.MarketingStrategyAgent",
            return_value=mocked_agent,
        ):
            response = self.client.post(
                "/dashboard/strategy-planner/",
                self._brief(),
            )
        self.assertEqual(response.status_code, 200)
        mocked_agent.generate.assert_called_once()
        self.assertEqual(self.Campaign.objects.count(), 0)
        body = response.content.decode()
        self.assertIn("Campaign Objective", body)
        self.assertIn("Target Audience", body)
        self.assertIn("Recommended Platform", body)
        self.assertIn("Strategy Summary", body)
        self.assertIn("Content Strategy", body)
        self.assertIn("Creative Direction", body)
        self.assertIn("Budget Strategy", body)
        self.assertIn("Recommended KPIs", body)
        self.assertIn("Messaging Angle", body)
        self.assertIn("CTA Strategy", body)
        self.assertIn("Why This Strategy?", body)
        self.assertIn("name=\"campaign_objective\"", body)
        self.assertIn("Create Campaign from Strategy", body)

    def test_malformed_strategy_fails_gracefully(self):
        from ai_services.services.marketing_strategy_agent import (
            StrategyGenerationError,
        )

        mocked_agent = MagicMock()
        mocked_agent.generate.side_effect = StrategyGenerationError(
            "The strategy response was not valid JSON."
        )
        with patch(
            "dashboard.views.MarketingStrategyAgent",
            return_value=mocked_agent,
        ):
            response = self.client.post(
                "/dashboard/strategy-planner/",
                self._brief(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.Campaign.objects.count(), 0)
        self.assertContains(response, "not valid JSON")

    def test_product_cannot_cross_company(self):
        other_product_id = (
            self.other_company.products.first().id
        )
        mocked_agent = MagicMock()
        with patch(
            "dashboard.views.MarketingStrategyAgent",
            return_value=mocked_agent,
        ):
            response = self.client.post(
                "/dashboard/strategy-planner/",
                self._brief(product_id=str(other_product_id)),
            )
        mocked_agent.generate.assert_not_called()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.Campaign.objects.count(), 0)

    def test_create_campaign_requires_explicit_action(self):
        mocked_agent = MagicMock()
        mocked_agent.generate.return_value = dict(SAMPLE_STRATEGY)
        with patch(
            "dashboard.views.MarketingStrategyAgent",
            return_value=mocked_agent,
        ):
            self.client.post("/dashboard/strategy-planner/", self._brief())
        self.assertEqual(self.Campaign.objects.count(), 0)

        create_payload = self._brief(action="create_campaign_from_strategy")
        create_payload.update(
            {
                "campaign_objective": SAMPLE_STRATEGY["campaign_objective"],
                "target_audience": SAMPLE_STRATEGY["target_audience"],
                "brief_target_audience": "University students aged 18-25.",
                "recommended_platform": "Instagram",
                "strategy_summary": SAMPLE_STRATEGY["strategy_summary"],
                "content_strategy": "\n".join(
                    SAMPLE_STRATEGY["content_strategy"]
                ),
                "creative_direction": SAMPLE_STRATEGY["creative_direction"],
                "budget_strategy": SAMPLE_STRATEGY["budget_strategy"],
                "recommended_kpis": "\n".join(
                    SAMPLE_STRATEGY["recommended_kpis"]
                ),
                "messaging_angle": SAMPLE_STRATEGY["messaging_angle"],
                "call_to_action_strategy": SAMPLE_STRATEGY[
                    "call_to_action_strategy"
                ],
                "reasoning": SAMPLE_STRATEGY["reasoning"],
            }
        )
        with patch("dashboard.views.MarketingStrategyAgent") as mocked:
            response = self.client.post(
                "/dashboard/strategy-planner/",
                create_payload,
            )
        mocked.assert_not_called()
        self.assertEqual(response.status_code, 302)
        campaign = self.Campaign.objects.get()
        self.assertEqual(campaign.company, self.company)
        self.assertEqual(campaign.product, self.product)
        self.assertEqual(campaign.platform, "Instagram")
        self.assertEqual(campaign.status, "Draft")
        self.assertEqual(str(campaign.budget), "1000.00")
        self.assertIn("iced coffee", campaign.objective.lower())
        self.assertIn("campaign=", response.url)

    def test_cannot_create_campaign_for_another_owner(self):
        payload = self._brief(
            action="create_campaign_from_strategy",
            company_id=str(self.other_company.id),
            product_id="",
        )
        payload["campaign_objective"] = "Should not save"
        response = self.client.post("/dashboard/strategy-planner/", payload)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.Campaign.objects.count(), 0)

    def test_manual_campaign_create_still_works(self):
        response = self.client.post(
            "/dashboard/campaigns/add/",
            {
                "company": self.company.id,
                "product": self.product.id,
                "campaign_name": "Manual September Push",
                "objective": "Hand-written objective",
                "platform": "Facebook",
                "budget": "250",
                "status": "Draft",
            },
        )
        self.assertEqual(response.status_code, 302)
        campaign = self.Campaign.objects.get(campaign_name="Manual September Push")
        self.assertEqual(campaign.platform, "Facebook")
        self.assertEqual(campaign.objective, "Hand-written objective")
        self.assertIn("/dashboard/ai-content/", response["Location"])
        self.assertIn(f"campaign={campaign.id}", response["Location"])
        self.assertIn("stage=generate", response["Location"])

    def test_ai_content_prefills_from_session_strategy(self):
        campaign = self.Campaign.objects.create(
            company=self.company,
            product=self.product,
            campaign_name="From strategy",
            objective="Increase iced coffee sales during September.",
            platform="Instagram",
            status="Draft",
        )
        session = self.client.session
        session["campaign_strategy_by_id"] = {
            str(campaign.id): {"strategy": SAMPLE_STRATEGY}
        }
        session.save()
        response = self.client.get(
            f"/dashboard/ai-content/?campaign={campaign.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Refreshing coffee")
        self.assertContains(response, "CTA strategy")

    def test_studio_restores_brief_and_saved_suggestions(self):
        from campaign.models import CampaignContent

        campaign = self.Campaign.objects.create(
            company=self.company,
            product=self.product,
            campaign_name="Studio Restore",
            objective="Keep written work",
            platform="Instagram",
            status="Draft",
        )
        CampaignContent.objects.create(
            campaign=campaign,
            title="Kept Suggestion",
            content_text="Suggestion 1 Title: Kept Suggestion",
            content_type="Post",
            platform="Instagram",
            language="Arabic",
            ai_generated=True,
        )
        session = self.client.session
        session["studio_creative_brief_by_campaign"] = {
            str(campaign.id): {
                "focus": "Keep this handwritten focus",
                "style": "Modern Minimal",
                "colors": "navy and cream",
                "background": "cafe counter",
                "composition": "Product Centered",
                "mood": "calm",
                "additional": "Do not erase",
            }
        }
        session.save()
        response = self.client.get(
            f"/dashboard/ai-content/?campaign={campaign.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Keep this handwritten focus")
        self.assertContains(response, "Kept Suggestion")
        self.assertContains(response, "← Back")
        self.assertContains(response, "Next →")

    def test_save_studio_state_keeps_brief_after_round_trip(self):
        campaign = self.Campaign.objects.create(
            company=self.company,
            product=self.product,
            campaign_name="Studio Round Trip",
            objective="Persist brief",
            platform="Instagram",
            status="Draft",
        )
        next_url = (
            f"/dashboard/ai-content/?campaign={campaign.id}"
        )
        response = self.client.post(
            "/dashboard/ai-content/",
            {
                "action": "save_studio_state",
                "campaign_id": str(campaign.id),
                "creative_focus": "Round-trip focus text",
                "creative_style": "Modern Minimal",
                "creative_colors": "teal",
                "creative_background": "studio",
                "creative_composition": "Product Centered",
                "creative_mood": "bold",
                "creative_additional": "notes stay",
                "next": next_url,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], next_url)
        restored = self.client.get(next_url)
        self.assertContains(restored, "Round-trip focus text")
        self.assertContains(restored, "notes stay")

    def test_save_studio_state_rejects_external_next(self):
        campaign = self.Campaign.objects.create(
            company=self.company,
            product=self.product,
            campaign_name="Studio Safety",
            objective="Safe next",
            platform="Instagram",
            status="Draft",
        )
        response = self.client.post(
            "/dashboard/ai-content/",
            {
                "action": "save_studio_state",
                "campaign_id": str(campaign.id),
                "creative_focus": "Safe focus",
                "next": "https://example.com/phish",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard/ai-content/", response["Location"])
        self.assertNotIn("example.com", response["Location"])


class DashboardThemeSmokeTests(TestCase):

    def setUp(self):
        from django.contrib.auth.models import User

        from campaign.models import Campaign
        from companies.models import Company
        from products.models import Product

        self.user = User.objects.create_user("themeuser", password="pass123")
        self.company = Company.objects.create(
            owner=self.user,
            company_name="Theme Co",
            industry="Retail",
        )
        self.product = Product.objects.create(
            company=self.company,
            product_name="Theme Product",
            category="Goods",
            price="10.00",
        )
        self.campaign = Campaign.objects.create(
            company=self.company,
            product=self.product,
            campaign_name="Theme Campaign",
            objective="Brand awareness",
            platform="Instagram",
            status="Draft",
        )
        self.client.force_login(self.user)

    def test_specialist_pages_render_without_legacy_blue_background(self):
        pages = [
            "/dashboard/",
            "/dashboard/companies/",
            "/dashboard/products/",
            "/dashboard/campaigns/",
            "/dashboard/strategy-planner/",
            "/dashboard/ai-content/",
            "/dashboard/knowledge-base/",
            "/dashboard/customer-support/",
            f"/dashboard/campaign/{self.campaign.id}/analytics/",
            "/dashboard/reports/",
        ]
        for url in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "#f4f7fb")

    def test_public_support_chat_hides_internals(self):
        response = self.client.get(f"/support/company/{self.company.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "ChromaDB")
        self.assertNotContains(response, "Cloudflare")
        self.assertNotContains(response, "#f4f7fb")


class SocialPerformanceImportTests(TestCase):

    def setUp(self):
        from django.contrib.auth.models import User

        from campaign.models import Campaign, CampaignPerformance
        from companies.models import Company
        from products.models import Product

        self.Campaign = Campaign
        self.CampaignPerformance = CampaignPerformance
        self.user = User.objects.create_user("socialuser", password="pass123")
        self.other = User.objects.create_user("socialother", password="pass123")
        self.company = Company.objects.create(
            owner=self.user,
            company_name="Social Co",
            industry="Retail",
        )
        self.other_company = Company.objects.create(
            owner=self.other,
            company_name="Other Social",
            industry="Retail",
        )
        self.product = Product.objects.create(
            company=self.company,
            product_name="Launch Mug",
            category="Goods",
            price="12.00",
        )
        self.campaign = Campaign.objects.create(
            company=self.company,
            product=self.product,
            campaign_name="Launch Mug campaign",
            objective="Promote the Launch Mug on campus.",
            platform="Instagram",
            status="Active",
            start_date=date.today() - timedelta(days=10),
            end_date=date.today() + timedelta(days=10),
        )
        self.other_campaign = Campaign.objects.create(
            company=self.other_company,
            campaign_name="Secret campaign",
            objective="Hidden",
            platform="Facebook",
            status="Draft",
        )
        self.client.force_login(self.user)
        self.url = f"/dashboard/campaign/{self.campaign.id}/analytics/"

    def test_analytics_page_loads_for_owner(self):
        with patch(
            "ai_services.clients.meta_insights_client.MetaInsightsClient.list_instagram_media"
        ) as mocked:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Social Media Performance")
        self.assertContains(response, "Fetch Social Posts")
        mocked.assert_not_called()

    def test_cross_owner_analytics_is_404(self):
        response = self.client.get(
            f"/dashboard/campaign/{self.other_campaign.id}/analytics/"
        )
        self.assertEqual(response.status_code, 404)

    def test_fetch_requires_post(self):
        response = self.client.get(
            self.url + "?action=fetch_social_posts"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "DEMO DATA")

    def test_demo_fetch_returns_labeled_simulated_posts(self):
        with self.settings(SOCIAL_PERFORMANCE_MODE="demo"):
            response = self.client.post(
                self.url,
                {
                    "action": "fetch_social_posts",
                    "social_platforms": "both",
                },
            )
        self.assertEqual(response.status_code, 302)
        page = self.client.get(self.url)
        self.assertContains(page, "DEMO DATA")
        self.assertContains(page, "Simulated social-media performance")
        self.assertContains(page, "demo-ig-launch")
        self.assertContains(page, "Suggested match")

    def test_no_selected_posts_returns_validation_error(self):
        with self.settings(SOCIAL_PERFORMANCE_MODE="demo"):
            self.client.post(
                self.url,
                {"action": "fetch_social_posts", "social_platforms": "instagram"},
            )
            response = self.client.post(
                self.url,
                {"action": "import_social_performance"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select at least one post to import.")
        self.assertEqual(self.CampaignPerformance.objects.count(), 0)

    def test_selected_demo_posts_persist_social_fields(self):
        from ai_services.analytics.service import AnalyticsService

        with self.settings(SOCIAL_PERFORMANCE_MODE="demo"):
            self.client.post(
                self.url,
                {"action": "fetch_social_posts", "social_platforms": "both"},
            )
            response = self.client.post(
                self.url,
                {
                    "action": "import_social_performance",
                    "social_post_id": [
                        "instagram:demo-ig-reel",
                        "facebook:demo-fb-announce",
                    ],
                },
            )
        self.assertEqual(response.status_code, 302)
        reel = self.CampaignPerformance.objects.get(
            campaign=self.campaign,
            external_post_id="demo-ig-reel",
        )
        facebook = self.CampaignPerformance.objects.get(
            campaign=self.campaign,
            external_post_id="demo-fb-announce",
        )
        self.assertEqual(reel.source, "demo")
        self.assertEqual(reel.platform, "Instagram")
        self.assertEqual(reel.impressions, 9400)
        self.assertEqual(reel.reach, 6200)
        self.assertEqual(reel.saves, 54)
        self.assertEqual(reel.views, 6203)
        self.assertEqual(reel.social_permalink, "https://www.instagram.com/reel/demo-reel/")
        self.assertEqual(reel.social_media_type, "REELS")
        self.assertEqual(facebook.clicks, 74)
        self.assertEqual(facebook.views, 0)
        self.assertEqual(facebook.impressions, 5200)
        analysis = AnalyticsService().get_campaign_analytics(self.campaign)
        self.assertEqual(analysis["summary"]["total_views"], 6203)
        self.assertEqual(analysis["summary"]["total_clicks"], 74)
        self.assertEqual(analysis["summary"]["total_impressions"], 9400 + 5200)
        self.assertEqual(analysis["summary"]["ctr_basis"], "impressions")
        self.assertEqual(
            analysis["summary"]["average_ctr"],
            round(74 / (9400 + 5200) * 100, 2),
        )
        follow = self.client.get(self.url)
        self.assertContains(follow, "were imported into campaign performance")
        self.assertContains(follow, "Already Imported")
        self.assertNotContains(follow, "not stored because the current")

    def test_duplicate_import_is_blocked_across_new_session(self):
        with self.settings(SOCIAL_PERFORMANCE_MODE="demo"):
            self.client.post(
                self.url,
                {"action": "fetch_social_posts", "social_platforms": "instagram"},
            )
            self.client.post(
                self.url,
                {
                    "action": "import_social_performance",
                    "social_post_id": ["instagram:demo-ig-launch"],
                },
            )
        other_client = Client()
        other_client.force_login(self.user)
        with self.settings(SOCIAL_PERFORMANCE_MODE="demo"):
            other_client.post(
                self.url,
                {"action": "fetch_social_posts", "social_platforms": "instagram"},
            )
            other_client.post(
                self.url,
                {
                    "action": "import_social_performance",
                    "social_post_id": ["instagram:demo-ig-launch"],
                },
            )
        self.assertEqual(
            self.CampaignPerformance.objects.filter(campaign=self.campaign).count(),
            1,
        )

    def test_same_external_id_on_other_platform_is_not_blocked(self):
        from ai_services.services.social_performance_importer import (
            SocialPerformanceImporter,
        )

        self.CampaignPerformance.objects.create(
            campaign=self.campaign,
            platform="Instagram",
            source="live",
            external_post_id="shared-id",
            views=1,
            clicks=0,
        )
        importer = SocialPerformanceImporter()
        facebook_post = {
            "platform": "facebook",
            "external_post_id": "shared-id",
            "caption": "Same looking id",
            "media_type": "POST",
            "permalink": "https://facebook.com/shared",
            "source": "live",
            "metrics": {
                "impressions": 20,
                "reach": 10,
                "likes": 1,
                "comments": 0,
                "shares": 0,
                "saved": None,
                "video_views": None,
                "clicks": 2,
            },
        }
        outcome = importer.import_selected(
            self.campaign,
            [facebook_post],
            ["facebook:shared-id"],
        )
        self.assertEqual(outcome["imported"], 1)
        self.assertEqual(
            self.CampaignPerformance.objects.filter(
                campaign=self.campaign,
                external_post_id="shared-id",
            ).count(),
            2,
        )

    def test_campaign_ctr_uses_total_clicks_over_impressions(self):
        from ai_services.analytics.service import AnalyticsService

        self.CampaignPerformance.objects.create(
            campaign=self.campaign,
            platform="Instagram",
            impressions=100,
            views=0,
            clicks=10,
        )
        self.CampaignPerformance.objects.create(
            campaign=self.campaign,
            platform="Facebook",
            impressions=10000,
            views=0,
            clicks=100,
        )
        summary = AnalyticsService().get_campaign_analytics(self.campaign)["summary"]
        self.assertEqual(summary["average_ctr"], 1.09)
        self.assertEqual(summary["ctr_basis"], "impressions")
        self.assertNotEqual(summary["average_ctr"], 5.5)

    def test_old_records_without_impressions_use_views_ctr(self):
        from ai_services.analytics.service import AnalyticsService

        self.CampaignPerformance.objects.create(
            campaign=self.campaign,
            platform="Facebook",
            views=1000,
            clicks=80,
        )
        summary = AnalyticsService().get_campaign_analytics(self.campaign)["summary"]
        self.assertIsNone(summary["total_impressions"])
        self.assertEqual(summary["ctr_basis"], "views")
        self.assertEqual(summary["average_ctr"], 8.0)

    def test_live_mode_uses_mocked_client_and_handles_error(self):
        from ai_services.clients.meta_insights_client import MetaInsightsError
        from ai_services.services.social_performance_importer import (
            SocialPerformanceImporter,
        )

        client = MagicMock()
        client.instagram_ready.return_value = True
        client.facebook_ready.return_value = False
        client.list_instagram_media.side_effect = MetaInsightsError(
            "Graph API request failed."
        )
        importer = SocialPerformanceImporter(insights_client=client)
        with self.settings(SOCIAL_PERFORMANCE_MODE="live"):
            result = importer.fetch_posts("instagram", self.campaign)
        self.assertEqual(result["posts"], [])
        self.assertIn("Graph API request failed", result["error"])
        client.list_instagram_media.assert_called_once()

    def test_live_instagram_and_facebook_normalize(self):
        from ai_services.services.social_performance_importer import (
            SocialPerformanceImporter,
        )

        client = MagicMock()
        client.instagram_ready.return_value = True
        client.facebook_ready.return_value = True
        client.list_instagram_media.return_value = [
            {
                "id": "ig-1",
                "caption": "Live launch",
                "media_type": "IMAGE",
                "timestamp": "2026-09-12T10:00:00+00:00",
                "permalink": "https://instagram.com/p/live",
                "like_count": 10,
                "comments_count": 2,
            }
        ]
        client.instagram_insights.return_value = {
            "impressions": 100,
            "reach": 80,
            "saved": 3,
        }
        client.list_facebook_posts.return_value = [
            {
                "id": "fb-1",
                "message": "Live facebook post",
                "created_time": "2026-09-13T10:00:00+00:00",
                "permalink_url": "https://facebook.com/live",
                "likes": {"summary": {"total_count": 4}},
                "comments": {"summary": {"total_count": 1}},
                "shares": {"count": 1},
            }
        ]
        client.facebook_insights.return_value = {
            "post_impressions": 50,
            "post_clicks": 5,
        }
        importer = SocialPerformanceImporter(insights_client=client)
        with self.settings(SOCIAL_PERFORMANCE_MODE="live"):
            result = importer.fetch_posts("both")
        self.assertIsNone(result["error"])
        self.assertEqual(len(result["posts"]), 2)
        instagram = result["posts"][0]
        facebook = result["posts"][1]
        self.assertEqual(instagram["platform"], "instagram")
        self.assertEqual(instagram["metrics"]["reach"], 80)
        self.assertIsNone(instagram["metrics"]["clicks"])
        self.assertEqual(facebook["metrics"]["clicks"], 5)
        payload, stored = importer.stored_fields_from_post(instagram)
        self.assertTrue(stored)
        self.assertEqual(payload["likes"], 10)
        self.assertEqual(payload["views"], 0)
        self.assertEqual(payload["impressions"], 100)
        self.assertEqual(payload["reach"], 80)
        self.assertEqual(payload["saves"], 3)
        self.assertEqual(payload["external_post_id"], "ig-1")
        self.assertEqual(payload["social_permalink"], "https://instagram.com/p/live")
        facebook_payload, _stored = importer.stored_fields_from_post(facebook)
        self.assertEqual(facebook_payload["clicks"], 5)
        self.assertEqual(facebook_payload["views"], 0)
        self.assertEqual(facebook_payload["impressions"], 50)

    def test_advisor_works_with_imported_performance_without_cloudflare(self):
        llm = MagicMock()
        llm.generate.return_value = """
        {
          "performance_insight": "Imported views are present.",
          "strengths": ["Views"],
          "weaknesses": ["No conversion metric recorded"],
          "recommended_actions": ["Keep measuring clicks"]
        }
        """
        self.CampaignPerformance.objects.create(
            campaign=self.campaign,
            platform="Instagram",
            views=100,
            clicks=8,
            likes=20,
            shares=2,
            comments=1,
        )
        from ai_services.analytics.service import AnalyticsService

        summary = AnalyticsService().get_campaign_analytics(self.campaign)["summary"]
        result = CampaignAdvisor(llm=llm).generate(self.campaign, summary)
        self.assertIn("Imported views", result["performance_insight"])
        llm.generate.assert_called_once()

    def test_manual_performance_still_works(self):
        self.CampaignPerformance.objects.create(
            campaign=self.campaign,
            platform="Facebook",
            views=50,
            clicks=5,
            likes=3,
            shares=1,
            comments=0,
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "50")

    def test_instagram_publisher_client_still_configured_check(self):
        from ai_services.services.instagram_publisher import InstagramPublisher

        publisher = InstagramPublisher()
        self.assertFalse(publisher.client.is_configured())


class CampaignIntelligenceTests(SimpleTestCase):

    def test_ctr_and_zero_denominator(self):
        from ai_services.analytics.intelligence import CampaignIntelligence

        intel = CampaignIntelligence()
        funnel = intel.build_funnel(
            {"total_impressions": 40000, "total_clicks": 1200}
        )
        self.assertEqual(funnel["ctr"], 3.0)
        empty = intel.build_funnel(
            {"total_impressions": 0, "total_clicks": 10}
        )
        self.assertIsNone(empty["ctr"])
        self.assertIsNone(funnel["click_to_conversion"])

    def test_missing_conversions_are_not_faked(self):
        from ai_services.analytics.intelligence import CampaignIntelligence

        campaign = SimpleNamespace(budget=None)
        metrics = CampaignIntelligence().visible_metrics(
            campaign,
            {"total_impressions": 100, "total_clicks": 4, "average_ctr": 4.0},
        )
        by_label = {item["label"]: item for item in metrics}
        self.assertFalse(by_label["Conversions"]["available"])
        self.assertFalse(by_label["Revenue"]["available"])
        self.assertFalse(by_label["ROI"]["available"])

    def test_one_platform_does_not_invent_winner(self):
        from ai_services.analytics.intelligence import CampaignIntelligence

        row = SimpleNamespace(
            platform="Instagram",
            clicks=10,
            views=100,
            likes=4,
            comments=1,
            shares=0,
            impressions=200,
            external_post_id="",
        )
        comparison = CampaignIntelligence().build_comparison([row])
        self.assertFalse(comparison["can_compare_platforms"])
        self.assertIsNone(comparison["best_platform"])

    def test_two_platforms_compare_relative_ctr(self):
        from ai_services.analytics.intelligence import CampaignIntelligence

        instagram = SimpleNamespace(
            platform="Instagram",
            clicks=41,
            views=0,
            likes=20,
            comments=5,
            shares=2,
            impressions=1000,
            external_post_id="ig-1",
        )
        facebook = SimpleNamespace(
            platform="Facebook",
            clicks=23,
            views=0,
            likes=4,
            comments=1,
            shares=0,
            impressions=1000,
            external_post_id="fb-1",
        )
        comparison = CampaignIntelligence().build_comparison(
            [instagram, facebook]
        )
        self.assertTrue(comparison["can_compare_platforms"])
        self.assertEqual(comparison["best_platform"], "Instagram")

    def test_empty_rows_insufficient_data(self):
        from ai_services.analytics.intelligence import CampaignIntelligence

        diagnosis = CampaignIntelligence().build_diagnosis(
            {},
            {"bottleneck": "none"},
            {},
            [],
        )
        self.assertEqual(diagnosis["status"], "Insufficient Data")

    def test_strategy_vs_outcome_does_not_claim_achievement(self):
        from ai_services.analytics.intelligence import CampaignIntelligence

        result = CampaignIntelligence().strategy_vs_outcome(
            {"campaign_objective": "Increase awareness and conversions."},
            {"total_impressions": 40000, "total_clicks": 1200, "average_ctr": 3.0},
            {"funnel_bottleneck": "Conversion data is not recorded."},
        )
        self.assertIn("cannot be claimed", result["assessment"])
        self.assertNotIn("achieved", result["assessment"].lower())


class CustomerVoiceAnalyzerUnitTests(SimpleTestCase):

    def test_percentages_computed_in_python(self):
        from ai_services.services.customer_voice_analyzer import (
            CustomerVoiceAnalyzer,
        )

        classified = [
            {
                "id": 1,
                "topic": "Delivery",
                "sentiment": "Negative",
                "concern": "Delivery",
                "question_theme": "When will my order arrive?",
            },
            {
                "id": 2,
                "topic": "Delivery",
                "sentiment": "Neutral",
                "concern": "Delivery",
                "question_theme": "When will my order arrive?",
            },
            {
                "id": 3,
                "topic": "Pricing",
                "sentiment": "Positive",
                "concern": None,
                "question_theme": None,
            },
        ]
        result = CustomerVoiceAnalyzer()._aggregate(
            classified,
            conversation_count=2,
            customer_message_count=3,
        )
        self.assertEqual(result["topics"][0]["label"], "Delivery")
        self.assertEqual(result["topics"][0]["count"], 2)
        self.assertEqual(result["topics"][0]["percentage"], 66.7)
        self.assertEqual(result["sentiment"]["Negative"]["percentage"], 33.3)
        self.assertEqual(result["concerns"][0]["count"], 2)

    def test_no_chunks_is_no_knowledge_found(self):
        from ai_services.services.customer_voice_analyzer import (
            CustomerVoiceAnalyzer,
        )

        retriever = MagicMock()
        retriever.retrieve_evidence.return_value = {
            "hits": [],
            "has_distances": False,
            "space": "l2",
        }
        analyzer = CustomerVoiceAnalyzer(retriever=retriever)
        gaps = analyzer.evaluate_knowledge_gaps(
            1,
            [{"label": "Delivery Time", "count": 12}],
        )
        self.assertEqual(gaps[0]["knowledge_support"], "No Knowledge Found")
        self.assertEqual(gaps[0]["retrieved_chunks"], 0)
        self.assertNotIn("confidence", gaps[0])

    def test_strong_distance_is_supported(self):
        from ai_services.services.customer_voice_analyzer import (
            CustomerVoiceAnalyzer,
        )

        retriever = MagicMock()
        retriever.retrieve_evidence.return_value = {
            "hits": [
                {
                    "text": "Orders usually arrive in 2–3 days.",
                    "metadata": {"source": "Shipping Policy.pdf"},
                    "distance": 0.22,
                }
            ],
            "has_distances": True,
            "space": "l2",
        }
        analyzer = CustomerVoiceAnalyzer(retriever=retriever)
        gaps = analyzer.evaluate_knowledge_gaps(
            1,
            [{"label": "Delivery Time", "count": 8}],
        )
        self.assertEqual(gaps[0]["knowledge_support"], "Supported")
        self.assertEqual(gaps[0]["relevance_label"], "High relevance")
        self.assertEqual(gaps[0]["retrieved_documents"], ["Shipping Policy.pdf"])
        self.assertEqual(gaps[0]["classification_basis"], "chroma_distance")

    def test_weak_distance_is_weak_support(self):
        from ai_services.services.customer_voice_analyzer import (
            CustomerVoiceAnalyzer,
        )

        retriever = MagicMock()
        retriever.retrieve_evidence.return_value = {
            "hits": [
                {
                    "text": "Our cafe opens at 8am.",
                    "metadata": {"source": "Hours.txt"},
                    "distance": 1.05,
                }
            ],
            "has_distances": True,
            "space": "l2",
        }
        analyzer = CustomerVoiceAnalyzer(retriever=retriever)
        gaps = analyzer.evaluate_knowledge_gaps(
            1,
            [{"label": "Delivery Time", "count": 8}],
        )
        self.assertEqual(gaps[0]["knowledge_support"], "Weak Support")
        self.assertEqual(gaps[0]["relevance_label"], "Moderate relevance")

    def test_multiple_irrelevant_chunks_are_not_supported(self):
        from ai_services.services.customer_voice_analyzer import (
            CustomerVoiceAnalyzer,
        )

        retriever = MagicMock()
        retriever.retrieve_evidence.return_value = {
            "hits": [
                {"text": "Unrelated menu item", "metadata": {}, "distance": 1.82},
                {"text": "Another unrelated chunk", "metadata": {}, "distance": 1.91},
                {"text": "Third unrelated chunk", "metadata": {}, "distance": 1.99},
            ],
            "has_distances": True,
            "space": "l2",
        }
        analyzer = CustomerVoiceAnalyzer(retriever=retriever)
        gaps = analyzer.evaluate_knowledge_gaps(
            1,
            [{"label": "Refund Policy", "count": 5}],
        )
        self.assertEqual(gaps[0]["knowledge_support"], "No Knowledge Found")
        self.assertEqual(gaps[0]["retrieved_chunks"], 3)
        self.assertEqual(gaps[0]["retrieved_documents"], [])
        self.assertEqual(gaps[0]["relevance_label"], "Low relevance")

    def test_missing_source_metadata_is_safe(self):
        from ai_services.services.customer_voice_analyzer import (
            CustomerVoiceAnalyzer,
        )

        retriever = MagicMock()
        retriever.retrieve_evidence.return_value = {
            "hits": [
                {"text": "Delivery is available.", "metadata": {}, "distance": 0.3},
            ],
            "has_distances": True,
            "space": "l2",
        }
        analyzer = CustomerVoiceAnalyzer(retriever=retriever)
        gaps = analyzer.evaluate_knowledge_gaps(
            1,
            [{"label": "Delivery", "count": 4}],
        )
        self.assertEqual(gaps[0]["retrieved_documents"], [])
        self.assertEqual(gaps[0]["knowledge_support"], "Supported")

    def test_distance_fallback_uses_chunk_count_heuristic(self):
        from ai_services.services.customer_voice_analyzer import (
            CustomerVoiceAnalyzer,
        )

        retriever = MagicMock()
        retriever.retrieve.return_value = {
            "documents": [["Shipping policy excerpt", "Hours excerpt"]],
            "metadatas": [[{"source": "Shipping Policy.pdf"}, {"source": "FAQ.pdf"}]],
        }
        analyzer = CustomerVoiceAnalyzer(retriever=retriever)
        gaps = analyzer.evaluate_knowledge_gaps(
            1,
            [{"label": "Delivery Time", "count": 8}],
        )
        self.assertEqual(gaps[0]["knowledge_support"], "Supported")
        self.assertEqual(gaps[0]["classification_basis"], "retrieval_availability")
        self.assertEqual(
            gaps[0]["retrieved_documents"],
            ["Shipping Policy.pdf", "FAQ.pdf"],
        )
        self.assertIsNone(gaps[0]["relevance_label"])


class KnowledgeSupportClassifyTests(SimpleTestCase):

    def test_l2_thresholds_match_chroma_lower_is_closer(self):
        from ai_services.analytics.knowledge_support import classify_hits

        strong = classify_hits(
            [{"text": "match", "metadata": {"source": "Policy.pdf"}, "distance": 0.2}],
            True,
            space="l2",
        )
        weak = classify_hits(
            [{"text": "maybe", "metadata": {}, "distance": 1.1}],
            True,
            space="l2",
        )
        poor = classify_hits(
            [
                {"text": "a", "metadata": {}, "distance": 1.8},
                {"text": "b", "metadata": {}, "distance": 1.9},
            ],
            True,
            space="l2",
        )
        self.assertEqual(strong["knowledge_support"], "Supported")
        self.assertEqual(weak["knowledge_support"], "Weak Support")
        self.assertEqual(poor["knowledge_support"], "No Knowledge Found")

    def test_source_label_does_not_invent_filename(self):
        from ai_services.analytics.knowledge_support import source_label

        self.assertEqual(source_label({"source": "Shipping Policy.pdf"}), "Shipping Policy.pdf")
        self.assertIsNone(source_label({}))
        self.assertIsNone(source_label(None))


class SupportAgentRegressionTests(SimpleTestCase):

    def test_support_agent_still_joins_retrieved_documents(self):
        from ai_services.rag.support_agent import SupportAgent

        agent = SupportAgent.__new__(SupportAgent)
        context = agent._context_from_results(
            {
                "documents": [["Delivery takes 2 days.", "We open at 8."]],
                "distances": [[0.1, 0.4]],
                "metadatas": [[{"source": "Shipping Policy.pdf"}]],
            }
        )
        self.assertIn("Delivery takes 2 days.", context)
        self.assertIn("We open at 8.", context)
        self.assertNotIn("Shipping Policy.pdf", context)


class MarketingIntelligenceViewTests(TestCase):

    def setUp(self):
        from django.contrib.auth.models import User

        from campaign.models import Campaign, CampaignPerformance
        from companies.models import Company
        from customer_support.models import SupportConversation, SupportMessage

        self.CampaignPerformance = CampaignPerformance
        self.SupportConversation = SupportConversation
        self.SupportMessage = SupportMessage
        self.user = User.objects.create_user("inteluser", password="pass123")
        self.other = User.objects.create_user("intelother", password="pass123")
        self.company = Company.objects.create(
            owner=self.user,
            company_name="Intel Cafe",
            industry="Restaurant",
        )
        self.other_company = Company.objects.create(
            owner=self.other,
            company_name="Other Intel",
            industry="Restaurant",
        )
        self.campaign = Campaign.objects.create(
            company=self.company,
            campaign_name="Awareness burst",
            objective="Increase awareness and conversions.",
            platform="Instagram",
            status="Active",
            start_date=date.today() - timedelta(days=5),
            end_date=date.today() + timedelta(days=5),
        )
        self.other_campaign = Campaign.objects.create(
            company=self.other_company,
            campaign_name="Hidden",
            objective="Hidden",
            platform="Facebook",
            status="Active",
        )
        self.client.force_login(self.user)
        self.url = f"/dashboard/campaign/{self.campaign.id}/analytics/"
        self.support_url = (
            f"/dashboard/customer-support/?company={self.company.id}"
        )

    def _customer_thread(self, company, texts):
        conversation = self.SupportConversation.objects.create(company=company)
        for text in texts:
            self.SupportMessage.objects.create(
                conversation=conversation,
                sender="Customer",
                message_text=text,
            )
        self.SupportMessage.objects.create(
            conversation=conversation,
            sender="AI",
            message_text="This is a terrible delay and I am angry.",
        )
        return conversation

    def test_campaign_analytics_get_does_not_call_ai(self):
        self.CampaignPerformance.objects.create(
            campaign=self.campaign,
            platform="Instagram",
            impressions=1000,
            views=800,
            clicks=40,
            likes=10,
            comments=2,
            shares=1,
        )
        with patch(
            "ai_services.clients.cloudflare_ai_client.CloudflareAIClient.generate"
        ) as llm:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        llm.assert_not_called()
        self.assertContains(response, "Campaign Funnel")
        self.assertContains(response, "Performance Diagnosis")
        self.assertContains(response, "Generate AI Analysis")
        self.assertContains(response, "Not available")
        self.assertContains(response, "fewer than two platforms")

    def test_totals_and_ctr_are_python_calculated(self):
        from ai_services.analytics.service import AnalyticsService

        self.CampaignPerformance.objects.create(
            campaign=self.campaign,
            platform="Instagram",
            impressions=40000,
            views=1000,
            clicks=1200,
        )
        summary = AnalyticsService().get_campaign_analytics(self.campaign)["summary"]
        self.assertEqual(summary["total_impressions"], 40000)
        self.assertEqual(summary["total_clicks"], 1200)
        self.assertEqual(summary["average_ctr"], 3.0)

    def test_ai_analysis_only_on_post(self):
        self.CampaignPerformance.objects.create(
            campaign=self.campaign,
            platform="Instagram",
            impressions=500,
            views=400,
            clicks=25,
        )
        llm = MagicMock()
        llm.generate.return_value = """
        {
          "performance_insight": "Impressions and clicks are recorded.",
          "executive_summary": "Awareness signals are present.",
          "strengths": ["Clicks exist"],
          "weaknesses": ["No conversions recorded"],
          "recommended_actions": ["Clarify delivery in creative"],
          "likely_interpretation": ["May indicate stronger awareness than conversion tracking"],
          "combined_insight": "Company customer questions about delivery may indicate a content gap.",
          "combined_actions": ["Include delivery details in the next CTA"]
        }
        """
        with patch("dashboard.views.CampaignAdvisor") as mocked:
            mocked.return_value.generate.return_value = CampaignAdvisor(
                llm=llm
            ).generate(
                self.campaign,
                {"total_views": 400, "total_clicks": 25, "average_ctr": 5.0},
            )
            get_response = self.client.get(self.url)
            self.assertEqual(get_response.status_code, 200)
            mocked.assert_not_called()
            post_response = self.client.post(
                self.url,
                {"action": "generate_ai_recommendations"},
            )
        self.assertEqual(post_response.status_code, 200)
        mocked.assert_called()
        self.assertContains(post_response, "Awareness signals are present.")
        self.assertContains(post_response, "AI Marketing Intelligence")

    def test_malformed_campaign_ai_does_not_crash(self):
        self.CampaignPerformance.objects.create(
            campaign=self.campaign,
            platform="Instagram",
            impressions=200,
            clicks=4,
        )
        llm = MagicMock()
        llm.generate.return_value = "Sorry, no JSON today."
        with patch(
            "dashboard.views.CampaignAdvisor",
            return_value=CampaignAdvisor(llm=llm),
        ):
            response = self.client.post(
                self.url,
                {"action": "generate_ai_recommendations"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Campaign analytics are still available.")
        self.assertContains(response, "Campaign Funnel")

    def test_support_get_excludes_ai_messages_and_skips_llm(self):
        self._customer_thread(
            self.company,
            [
                "When will my order arrive?",
                "Is delivery available this week?",
                "The shipping is late.",
            ],
        )
        with patch(
            "ai_services.clients.cloudflare_ai_client.CloudflareAIClient.generate"
        ) as llm:
            response = self.client.get(self.support_url)
        self.assertEqual(response.status_code, 200)
        llm.assert_not_called()
        self.assertContains(response, "Customer Voice Intelligence")
        self.assertContains(response, "Delivery")
        self.assertContains(response, "Analyze Customer Voice")

    def test_ai_replies_are_not_customer_sentiment(self):
        from ai_services.services.customer_voice_analyzer import (
            CustomerVoiceAnalyzer,
        )

        self._customer_thread(
            self.company,
            [
                "Thanks, this is great.",
                "Thanks, love it.",
                "Perfect, thank you.",
            ],
        )
        result = CustomerVoiceAnalyzer().analyze(self.company, use_ai=False)
        self.assertEqual(result["customer_message_count"], 3)
        self.assertGreater(result["sentiment"]["Positive"]["count"], 0)
        self.assertEqual(result["sentiment"]["Negative"]["count"], 0)

    def test_small_dataset_insufficient_data(self):
        from ai_services.services.customer_voice_analyzer import (
            CustomerVoiceAnalyzer,
        )

        self._customer_thread(self.company, ["Hi"])
        result = CustomerVoiceAnalyzer().analyze(self.company, use_ai=False)
        self.assertTrue(result["insufficient_data"])

    def test_empty_conversations_handled(self):
        from ai_services.services.customer_voice_analyzer import (
            CustomerVoiceAnalyzer,
        )

        result = CustomerVoiceAnalyzer().analyze(self.company, use_ai=False)
        self.assertTrue(result["empty"])
        self.assertEqual(result["customer_message_count"], 0)

    def test_customer_voice_ai_only_on_post_and_malformed_safe(self):
        self._customer_thread(
            self.company,
            [
                "When will delivery arrive?",
                "How much does it cost?",
                "Is the product available?",
            ],
        )
        llm = MagicMock()
        llm.generate.return_value = "not-json"
        retriever = MagicMock()
        retriever.retrieve.return_value = {"documents": [[]], "metadatas": [[]]}
        with patch(
            "dashboard.views.CustomerVoiceAnalyzer"
        ) as mocked:
            from ai_services.services.customer_voice_analyzer import (
                CustomerVoiceAnalyzer,
            )

            mocked.return_value = CustomerVoiceAnalyzer(
                llm=llm,
                retriever=retriever,
            )
            get_response = self.client.get(self.support_url)
            self.assertEqual(get_response.status_code, 200)
            retriever.retrieve.assert_not_called()
            post_response = self.client.post(
                self.support_url,
                {
                    "action": "analyze_customer_voice",
                    "company": str(self.company.id),
                },
            )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(post_response.status_code, 200)
        self.assertContains(
            post_response,
            "Customer Voice AI summary could not be generated.",
        )
        self.assertContains(post_response, "No Knowledge Found")
        retriever.retrieve.assert_called()

    def test_combined_insight_uses_same_company_only(self):
        from ai_services.analytics.intelligence import CampaignIntelligence
        from ai_services.services.customer_voice_analyzer import (
            CustomerVoiceAnalyzer,
        )

        self._customer_thread(
            self.company,
            [
                "When will delivery arrive?",
                "The price is high.",
                "Is delivery available?",
            ],
        )
        self._customer_thread(
            self.other_company,
            [
                "Refund now",
                "Refund please",
                "I need a refund immediately",
            ],
        )
        voice = CustomerVoiceAnalyzer().analyze(
            self.campaign.company,
            campaign=self.campaign,
            use_ai=False,
        )
        labels = [item["label"] for item in voice["topics"]]
        self.assertTrue(
            any("Delivery" in label or "Pricing" in label for label in labels)
        )
        self.assertNotIn("Refunds", labels)
        combined = CampaignIntelligence().combined_context(self.campaign, voice)
        self.assertIn("company", combined["caution"].lower())
        self.assertNotIn("caused", combined["label"].lower())
        response = self.client.get(self.url)
        self.assertContains(
            response,
            "Customer Support Signals During Campaign Period",
        )
        self.assertContains(
            response,
            "not evidence that the campaign caused",
        )
        other_page = Client()
        other_page.force_login(self.user)
        hidden = other_page.get(
            f"/dashboard/campaign/{self.other_campaign.id}/analytics/"
        )
        self.assertEqual(hidden.status_code, 404)

