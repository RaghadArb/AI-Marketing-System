from django.core.management.base import BaseCommand
from pathlib import Path

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
from ai_services.evaluation.metrics import chatbot_summary, clamp_unit


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
    "company_profile_context",
    "available_generation_evidence",
]


def _successful(row):
    return (
        row.get("status") == "evaluated"
        and row.get("error") is None
        and row.get("grading_error") is None
        and clamp_unit(row.get("correctness_score")) is not None
        and clamp_unit(row.get("faithfulness_score")) is not None
        and clamp_unit(row.get("relevance_score")) is not None
        and row.get("hallucinated") is not None
    )


def _merge_by_id(existing, updates):
    merged = {str(row.get("id")): row for row in existing if row.get("id") is not None}
    order = [str(row.get("id")) for row in existing if row.get("id") is not None]
    for row in updates:
        key = str(row.get("id"))
        if key not in merged:
            order.append(key)
        merged[key] = row
    return [merged[key] for key in order]


def _select_cases(cases, start=1, end=None):
    start = max(1, int(start))
    end = len(cases) if end is None else int(end)
    if end < start:
        raise ValueError("--end must be greater than or equal to --start")
    return cases[start - 1:end]


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
        parser.add_argument("--start", type=int, default=1)
        parser.add_argument("--end", type=int, default=None)
        parser.add_argument("--resume", action="store_true")
        parser.add_argument(
            "--output-dir",
            default=str(DEFAULT_RESULTS_DIR),
            help="Directory for JSON/CSV results",
        )

    def handle(self, *args, **options):
        cases = load_json(options["dataset"])
        selected = _select_cases(cases, options["start"], options["end"])
        out_dir = options["output_dir"]
        result_path = f"{out_dir}/chatbot_evaluation_results.json"
        existing = load_json(result_path) if options["resume"] and Path(result_path).exists() else []
        completed = {str(row.get("id")) for row in existing if _successful(row)}
        pending = [case for case in selected if str(case.get("id")) not in completed]
        agent = TracingSupportAgent()
        updates = []
        for case in pending:
            batch, _ = run_chatbot_evaluation([case], agent=agent, grader_llm=agent.llm)
            updates.extend(batch)
            # Merge after every case so interruption preserves prior successes.
            existing = _merge_by_id(existing, batch)
            write_json(result_path, existing)
        records = _merge_by_id(existing, updates) if options["resume"] else _merge_by_id([], updates)
        if options["resume"]:
            records = _merge_by_id(existing, [])
        summary = chatbot_summary(records)
        evaluated_ids = {str(row.get("id")) for row in records if _successful(row)}
        summary.update({
            "successful_evaluated_cases": len(evaluated_ids),
            "skipped_cases": len(selected) - len(pending),
            "failed_cases": sum(1 for row in records if row.get("status") == "failed"),
            "pending_cases": max(0, len(cases) - len(evaluated_ids)),
        })
        csv_rows = []
        for row in records:
            csv_row = dict(row)
            sources = csv_row.get("retrieved_sources") or []
            csv_row["retrieved_sources"] = "; ".join(str(item) for item in sources)
            csv_rows.append(csv_row)
        write_json(result_path, records)
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
