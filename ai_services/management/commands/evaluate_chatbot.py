from django.core.management.base import BaseCommand

from ai_services.evaluation.chatbot import (
    TracingSupportAgent,
    run_chatbot_evaluation,
)
from ai_services.evaluation.io import (
    CHATBOT_TEMPLATE,
    DEFAULT_RESULTS_DIR,
    load_json,
    write_csv,
    write_json,
)


CHATBOT_CSV_FIELDS = [
    "id",
    "company_id",
    "status",
    "question",
    "ground_truth",
    "generated_answer",
    "retrieved_context",
    "retrieved_sources",
    "retrieval_hit",
    "correctness_score",
    "is_correct",
    "faithfulness_score",
    "relevance_score",
    "hallucinated",
    "grading_error",
    "error",
]


class Command(BaseCommand):
    help = (
        "Evaluate the customer-support RAG chatbot against a JSON test set. "
        "Does not run during tests or Django startup."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dataset",
            default=str(CHATBOT_TEMPLATE),
            help="Path to chatbot_test_set.json",
        )
        parser.add_argument(
            "--output-dir",
            default=str(DEFAULT_RESULTS_DIR),
            help="Directory for JSON/CSV results",
        )

    def handle(self, *args, **options):
        cases = load_json(options["dataset"])
        agent = TracingSupportAgent()
        records, summary = run_chatbot_evaluation(
            cases,
            agent=agent,
            grader_llm=agent.llm,
        )
        out_dir = options["output_dir"]
        csv_rows = []
        for row in records:
            csv_row = dict(row)
            sources = csv_row.get("retrieved_sources") or []
            csv_row["retrieved_sources"] = "; ".join(str(item) for item in sources)
            csv_rows.append(csv_row)
        write_json(f"{out_dir}/chatbot_evaluation_results.json", records)
        write_csv(
            f"{out_dir}/chatbot_evaluation_results.csv",
            csv_rows,
            CHATBOT_CSV_FIELDS,
        )
        write_json(f"{out_dir}/chatbot_evaluation_summary.json", summary)
        self.stdout.write(self.style.SUCCESS("Chatbot evaluation finished."))
        self.stdout.write(
            f"Evaluated: {summary.get('evaluated_cases')} / "
            f"{summary.get('total_test_cases')}"
        )
        accuracy = summary.get("answer_accuracy_percent")
        self.stdout.write(
            "Answer accuracy %: "
            f"{accuracy if accuracy is not None else 'N/A'}"
        )
        self.stdout.write(f"Wrote results under {out_dir}")
