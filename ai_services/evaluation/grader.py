import json
import re


class GradingUnavailable(RuntimeError):
    """LLM grader returned nothing usable. Do not invent a score."""


def extract_json_object(text):
    raw = str(text or "").strip()
    if not raw:
        raise GradingUnavailable("Empty grader response.")
    # LLMs commonly wrap otherwise valid JSON in a markdown code fence.
    # Remove only a complete outer fence; do not turn arbitrary prose into JSON.
    fenced = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.IGNORECASE | re.DOTALL
    )
    if fenced:
        raw = fenced.group(1).strip()
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        raise GradingUnavailable("Grader response was not valid JSON.")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise GradingUnavailable("Grader JSON could not be parsed.") from exc
    if not isinstance(payload, dict):
        raise GradingUnavailable("Grader JSON was not an object.")
    return payload


def grade_with_llm(llm, prompt, system_prompt, grader_name="grader"):
    if llm is None:
        raise GradingUnavailable("No LLM client was provided.")
    response = llm.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.1,
        max_tokens=800,
    )
    try:
        payload = extract_json_object(response)
        return _validate_grader_payload(payload, grader_name)
    except GradingUnavailable as exc:
        raise GradingUnavailable(f"{grader_name}: {exc}") from exc


def _validate_grader_payload(payload, grader_name):
    key = {"correctness": "correctness", "faithfulness": "faithfulness", "relevance": "relevance"}.get(grader_name)
    if not key:
        return payload
    block = payload.get(key)
    if not isinstance(block, dict) or "score" not in block:
        raise GradingUnavailable(f"{grader_name}: missing {key}.score")
    try:
        score = float(block["score"])
    except (TypeError, ValueError):
        raise GradingUnavailable(f"{grader_name}: invalid {key}.score")
    if not 0 <= score <= 1:
        raise GradingUnavailable(f"{grader_name}: {key}.score out of range")
    return payload


CHATBOT_GRADER_SYSTEM = (
    "You are a strict evaluation grader for a customer-support RAG chatbot. "
    "Return JSON only. Never invent evidence that is not in the inputs."
)


def chatbot_grader_prompt(question, ground_truth, generated_answer, retrieved_context):
    return f"""
Grade the chatbot answer. Use only the provided materials.

Return JSON with this exact shape:
{{
  "correctness": {{"score": 0.0, "reason": ""}},
  "faithfulness": {{"score": 0.0, "reason": ""}},
  "relevance": {{"score": 0.0, "reason": ""}},
  "unsupported_important_claims": false
}}

Scoring rules:
- correctness: semantic agreement with ground_truth, 0 to 1.
- faithfulness: generated_answer is supported by retrieved_context, 0 to 1.
  Score 0 if retrieved_context is empty and the answer asserts company facts.
- relevance: generated_answer directly addresses the question, 0 to 1.
- unsupported_important_claims: true if the answer contains important claims
  not supported by retrieved_context.

Customer question:
{question}

Ground truth:
{ground_truth}

Generated answer:
{generated_answer}

Retrieved context:
{retrieved_context or "[NO RETRIEVED CONTEXT]"}
""".strip()


def chatbot_correctness_prompt(question, ground_truth, generated_answer):
    return f'''Return JSON only: {{"correctness": {{"score": 0.0, "reason": ""}}}}.
Score semantic agreement with the ground truth from 0 to 1.
Question: {question}
Ground truth: {ground_truth}
Generated answer: {generated_answer}'''.strip()


def chatbot_faithfulness_prompt(generated_answer, available_generation_evidence):
    return f'''Return JSON only: {{"faithfulness": {{"score": 0.0, "reason": ""}}, "unsupported_important_claims": false}}.
Score whether every important claim in the answer is supported by the available evidence. Do not use outside knowledge.
Generated answer: {generated_answer}
Available generation evidence:
{available_generation_evidence or "[NO AVAILABLE EVIDENCE]"}'''.strip()


def chatbot_relevance_prompt(question, generated_answer):
    return f'''Return JSON only: {{"relevance": {{"score": 0.0, "reason": ""}}}}.
Score whether the answer directly addresses the question from 0 to 1.
Question: {question}
Generated answer: {generated_answer}'''.strip()


CONTENT_GRADER_SYSTEM = (
    "You are a strict marketing-content evaluator. Return JSON only. "
    "Do not treat this as classification accuracy."
)


def content_grader_prompt(case, suggestion_text):
    facts = case.get("factual_information") or case.get(
        "factual_product_company_information"
    ) or ""
    brief = case.get("creative_brief") or {}
    return f"""
Score this marketing suggestion on five criteria from 1 to 5.

Return JSON with this exact shape:
{{
  "campaign_relevance": {{"score": 1, "reason": ""}},
  "factual_consistency": {{"score": 1, "reason": ""}},
  "platform_appropriateness": {{"score": 1, "reason": ""}},
  "language_quality": {{"score": 1, "reason": ""}},
  "cta_quality": {{"score": 1, "reason": ""}}
}}

1 = very poor, 5 = excellent.
Penalize invented product or company claims that are not in the facts.
Do not reward unsupported discounts, prices, or statistics.

Company: {case.get("company") or ""}
Product: {case.get("product") or ""}
Campaign objective: {case.get("campaign_objective") or ""}
Platform: {case.get("platform") or ""}
Target audience: {case.get("target_audience") or ""}
Creative brief: {brief}
Factual product/company information:
{facts}

Generated suggestion:
{suggestion_text}
""".strip()
