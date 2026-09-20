from django.core.management.base import BaseCommand

from ai_services.evaluation.io import load_json
from ai_services.evaluation.metrics import retrieval_hit
from ai_services.rag.retriever import Retriever


class Command(BaseCommand):
    help = "Run local retrieval-only diagnostics; never calls a generation provider."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", required=True)
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--start", type=int, default=1)
        parser.add_argument("--end", type=int, default=None)

    def handle(self, *args, **options):
        cases = load_json(options["dataset"])[options["start"] - 1:options["end"]]
        retriever = Retriever()
        hits = {1: 0, 3: 0, 5: 0}
        failed = []
        for case in cases:
            result = retriever.retrieve(case["question"], options["company_id"], n_results=5)
            docs = (result.get("documents") or [[]])[0]
            metas = (result.get("metadatas") or [[]])[0]
            sources = [str((m or {}).get("source", "")) for m in metas]
            found = []
            for k in hits:
                ok = retrieval_hit("\n".join(docs[:k]), sources[:k], case.get("expected_source", ""), case.get("expected_knowledge_text", ""), case.get("expected_answer", ""))
                if ok:
                    hits[k] += 1
                    found.append(k)
            if 5 not in found:
                failed.append(case.get("id"))
        total = len(cases)
        self.stdout.write(f"Total: {total}")
        for k in hits:
            self.stdout.write(f"Hit Rate @{k}: {(hits[k] / total * 100) if total else 0:.2f}%")
        self.stdout.write(f"Failed IDs: {', '.join(str(x) for x in failed)}")
