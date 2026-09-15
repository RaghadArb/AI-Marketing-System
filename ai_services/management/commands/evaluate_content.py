from django.core.management.base import BaseCommand

from ai_services.evaluation.content import run_content_evaluation
from ai_services.evaluation.io import (
    CONTENT_TEMPLATE,
    DEFAULT_RESULTS_DIR,
    load_json,
    write_csv,
    write_json,
)
from ai_services.services.content_generator import ContentGenerator


CONTENT_CSV_FIELDS = [
    "id",
    "case_id",
    "campaign_id",
    "suggestion_index",
    "status",
    "campaign_relevance",
    "factual_consistency",
    "platform_appropriateness",
    "language_quality",
    "cta_quality",
    "total_score",
    "quality_percentage",
    "grading_error",
    "error",
    "generated_content",
]


class Command(BaseCommand):
    help = (
        "Evaluate the marketing ContentGenerator against a JSON test set. "
        "Does not run during tests or Django startup."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dataset",
            default=str(CONTENT_TEMPLATE),
            help="Path to content_test_set.json",
        )
        parser.add_argument(
            "--output-dir",
            default=str(DEFAULT_RESULTS_DIR),
            help="Directory for JSON/CSV results",
        )

    def handle(self, *args, **options):
        cases = load_json(options["dataset"])
        generator = ContentGenerator()
        records, summary = run_content_evaluation(
            cases,
            generator=generator,
            grader_llm=generator.ai_client,
        )
        out_dir = options["output_dir"]
        write_json(f"{out_dir}/content_evaluation_results.json", records)
        write_csv(
            f"{out_dir}/content_evaluation_results.csv",
            records,
            CONTENT_CSV_FIELDS,
        )
        write_json(f"{out_dir}/content_evaluation_summary.json", summary)
        self.stdout.write(self.style.SUCCESS("Content evaluation finished."))
        quality = summary.get("overall_content_quality")
        self.stdout.write(
            "Marketing Content Quality Score: "
            f"{quality if quality is not None else 'N/A'}"
        )
        self.stdout.write(f"Wrote results under {out_dir}")
