from ai_services.evaluation.grader import (
    GradingUnavailable,
    chatbot_grader_prompt,
    CHATBOT_GRADER_SYSTEM,
    grade_with_llm,
    chatbot_correctness_prompt,
    chatbot_faithfulness_prompt,
    chatbot_relevance_prompt,
)
from ai_services.evaluation.metrics import (
    clamp_unit,
    is_correct,
    retrieval_hit,
    chatbot_summary,
)
from ai_services.evaluation.io import json_ready
from ai_services.rag.support_agent import SupportAgent
from ai_services.analytics.knowledge_support import (
    parse_query_results,
    source_label,
)


class TracingSupportAgent(SupportAgent):
    """Same SupportAgent pipeline, with last retrieval captured for eval."""

    def __init__(self):
        super().__init__()
        self.last_documents = None
        self.last_context = ""
        self.last_company_profile = ""

    def _company_profile(self, company):
        profile = super()._company_profile(company)
        self.last_company_profile = profile
        return profile

    def _retrieve_context(self, question, company):
        documents = self.retriever.retrieve(
            question=question,
            company_id=company.id,
        )
        self.last_documents = documents
        context = self._context_from_results(documents)
        self.last_context = context
        return context


def _sources_from_documents(documents):
    hits, _has_distances = parse_query_results(documents or {})
    sources = []
    chunks = []
    for hit in hits:
        chunks.append(hit.get("text") or "")
        label = source_label(hit.get("metadata") or {})
        if label:
            sources.append(label)
        metadata = hit.get("metadata") or {}
        for key in ("id", "document_id", "chunk_id"):
            value = metadata.get(key)
            if value:
                sources.append(str(value))
    ids = (documents or {}).get("ids") or []
    if ids and isinstance(ids[0], list):
        sources.extend(str(item) for item in ids[0] if item)
    return chunks, list(dict.fromkeys(sources))


def _nested_score(payload, key):
    block = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(block, dict):
        return None, None
    return clamp_unit(block.get("score")), str(block.get("reason") or "").strip() or None


def evaluate_chatbot_case(case, agent, grader_llm=None):
    question = str(case.get("question") or "").strip()
    ground_truth = str(
        case.get("expected_answer") or case.get("ground_truth") or ""
    ).strip()
    company_id = case.get("company_id") or case.get("company")
    record = {
        "id": case.get("id"),
        "question": question,
        "ground_truth": ground_truth,
        "company_id": company_id,
        "expected_source": case.get("expected_source") or "",
        "expected_knowledge_text": case.get("expected_knowledge_text") or "",
        "generated_answer": None,
        "retrieved_context": None,
        "company_profile_context": None,
        "available_generation_evidence": None,
        "retrieved_chunks": [],
        "retrieved_sources": [],
        "correctness_score": None,
        "correctness_reason": None,
        "faithfulness_score": None,
        "faithfulness_reason": None,
        "relevance_score": None,
        "relevance_reason": None,
        "retrieval_hit": None,
        "hallucinated": None,
        "is_correct": None,
        "grading_error": None,
        "human_scores": None,
        "status": "failed",
        "error": None,
    }
    if not question:
        record["error"] = "Question is missing."
        return record
    if company_id in (None, "", "REPLACE_WITH_COMPANY_ID"):
        record["status"] = "skipped"
        record["error"] = (
            "Set company_id to a real Company primary key before running."
        )
        return record

    try:
        agent.last_documents = None
        agent.last_context = ""
        if hasattr(agent, "last_company_profile"):
            agent.last_company_profile = ""
        answer = agent.generate_answer(
            question=question,
            company_id=int(company_id),
        )
    except Exception as exc:
        record["error"] = str(exc)
        return record

    chunks, sources = _sources_from_documents(agent.last_documents)
    context = agent.last_context or "\n".join(chunks)
    record["generated_answer"] = answer
    record["retrieved_context"] = context
    profile = getattr(agent, "last_company_profile", "")
    record["company_profile_context"] = profile if isinstance(profile, str) else ""
    record["available_generation_evidence"] = "\n\n".join(
        item for item in (record["company_profile_context"], context) if item
    )
    record["retrieved_chunks"] = chunks
    record["retrieved_sources"] = sources
    record["retrieval_hit"] = retrieval_hit(
        retrieved_text=context,
        retrieved_sources=sources,
        expected_source=record["expected_source"],
        expected_knowledge_text=record["expected_knowledge_text"],
        ground_truth=ground_truth,
    )
    record["status"] = "evaluated"

    if grader_llm is None:
        record["grading_error"] = "LLM grader was not available."
        return record

    try:
        correctness = grade_with_llm(grader_llm, chatbot_correctness_prompt(question, ground_truth, answer), CHATBOT_GRADER_SYSTEM, "correctness")
        faithfulness = grade_with_llm(grader_llm, chatbot_faithfulness_prompt(answer, record["available_generation_evidence"]), CHATBOT_GRADER_SYSTEM, "faithfulness")
        relevance = grade_with_llm(grader_llm, chatbot_relevance_prompt(question, answer), CHATBOT_GRADER_SYSTEM, "relevance")
        graded = {
            "correctness": correctness.get("correctness"),
            "faithfulness": faithfulness.get("faithfulness"),
            "relevance": relevance.get("relevance"),
            "unsupported_important_claims": faithfulness.get("unsupported_important_claims"),
        }
    except GradingUnavailable as exc:
        record["grading_error"] = str(exc)
        return record
    except Exception as exc:
        record["grading_error"] = str(exc)
        return record

    record["correctness_score"], record["correctness_reason"] = _nested_score(
        graded, "correctness"
    )
    record["faithfulness_score"], record["faithfulness_reason"] = _nested_score(
        graded, "faithfulness"
    )
    record["relevance_score"], record["relevance_reason"] = _nested_score(
        graded, "relevance"
    )
    if "unsupported_important_claims" in graded:
        record["hallucinated"] = bool(graded.get("unsupported_important_claims"))
    record["is_correct"] = is_correct(record["correctness_score"])
    return record


def run_chatbot_evaluation(cases, agent=None, grader_llm=None):
    agent = agent or TracingSupportAgent()
    records = [
        json_ready(evaluate_chatbot_case(case, agent, grader_llm=grader_llm))
        for case in cases
    ]
    return records, chatbot_summary(records)
