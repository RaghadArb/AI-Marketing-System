CORRECTNESS_THRESHOLD = 0.8


def clamp_unit(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return max(0.0, min(1.0, number))


def clamp_five(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return max(1.0, min(5.0, number))


def mean(values):
    numbers = [float(item) for item in values if item is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def percent(numerator, denominator):
    if not denominator:
        return None
    return (numerator / denominator) * 100.0


def is_correct(correctness_score, threshold=CORRECTNESS_THRESHOLD):
    score = clamp_unit(correctness_score)
    if score is None:
        return None
    return score >= threshold


def retrieval_hit(
    retrieved_text,
    retrieved_sources,
    expected_source="",
    expected_knowledge_text="",
    ground_truth="",
):
    """
    Deterministic retrieval hit.

    True if retrieved context/sources contain the expected source label,
    expected knowledge excerpt, or a substantial overlap with the
    ground-truth answer. Returns None when there is no expected
    retrieval target to judge against.
    """
    expected_source = str(expected_source or "").strip()
    expected_knowledge = str(expected_knowledge_text or "").strip()
    ground_truth = str(ground_truth or "").strip()
    if not expected_source and not expected_knowledge and not ground_truth:
        return None

    blob = " ".join(
        [
            str(retrieved_text or ""),
            " ".join(str(item) for item in (retrieved_sources or [])),
        ]
    ).lower()

    if not blob.strip():
        return False

    if expected_source and expected_source.lower() in blob:
        return True
    if expected_knowledge and expected_knowledge.lower() in blob:
        return True
    if ground_truth:
        tokens = [
            token
            for token in _tokenize(ground_truth)
            if len(token) >= 4
        ]
        if tokens:
            matches = sum(1 for token in tokens if token in blob)
            return matches / len(tokens) >= 0.5
        return ground_truth.lower() in blob
    return False


def _tokenize(text):
    return [
        part
        for part in "".join(
            ch.lower() if ch.isalnum() else " "
            for ch in str(text or "")
        ).split()
        if part
    ]


def chatbot_summary(records):
    total = len(records)
    evaluated = [
        row
        for row in records
        if row.get("status") == "evaluated"
    ]
    correctness = [clamp_unit(row.get("correctness_score")) for row in evaluated]
    valid_correctness = [item for item in correctness if item is not None]
    correct = sum(1 for item in valid_correctness if item >= CORRECTNESS_THRESHOLD)
    hits = [row.get("retrieval_hit") for row in evaluated]
    valid_hits = [item for item in hits if item is not None]
    faithfulness = [clamp_unit(row.get("faithfulness_score")) for row in evaluated]
    relevance = [clamp_unit(row.get("relevance_score")) for row in evaluated]
    hallucinations = [row.get("hallucinated") for row in evaluated]
    valid_hallucinations = [item for item in hallucinations if item is not None]

    return {
        "total_test_cases": total,
        "evaluated_cases": len(evaluated),
        "skipped_or_failed_cases": total - len(evaluated),
        "answer_accuracy_percent": percent(correct, len(valid_correctness)),
        "average_correctness_score": mean(valid_correctness),
        "correctness_valid_n": len(valid_correctness),
        "retrieval_hit_rate_percent": percent(
            sum(1 for item in valid_hits if item),
            len(valid_hits),
        ),
        "retrieval_hit_valid_n": len(valid_hits),
        "average_faithfulness": mean(
            [item for item in faithfulness if item is not None]
        ),
        "average_answer_relevance": mean(
            [item for item in relevance if item is not None]
        ),
        "hallucination_rate_percent": percent(
            sum(1 for item in valid_hallucinations if item),
            len(valid_hallucinations),
        ),
        "hallucination_valid_n": len(valid_hallucinations),
        "correctness_threshold": CORRECTNESS_THRESHOLD,
        "formulas": {
            "answer_accuracy": (
                "correct(correctness_score >= 0.8) / "
                "valid_correctness_n * 100"
            ),
            "retrieval_hit_rate": (
                "retrieval_hits / valid_retrieval_n * 100"
            ),
            "hallucination_rate": (
                "hallucinated_responses / valid_hallucination_n * 100"
            ),
        },
    }


def content_quality_from_scores(scores):
    keys = (
        "campaign_relevance",
        "factual_consistency",
        "platform_appropriateness",
        "language_quality",
        "cta_quality",
    )
    values = [clamp_five(scores.get(key)) for key in keys]
    if any(item is None for item in values):
        return None
    total = sum(values)
    return {
        "campaign_relevance": values[0],
        "factual_consistency": values[1],
        "platform_appropriateness": values[2],
        "language_quality": values[3],
        "cta_quality": values[4],
        "total_score": total,
        "maximum": 25,
        "quality_percentage": (total / 25.0) * 100.0,
    }


def content_summary(records):
    total = len(records)
    evaluated = [
        row
        for row in records
        if row.get("status") == "evaluated"
        and row.get("quality_percentage") is not None
    ]
    percentages = [row.get("quality_percentage") for row in evaluated]
    return {
        "metric_name": "Marketing Content Quality Score",
        "total_test_cases": total,
        "evaluated_outputs": len(evaluated),
        "skipped_or_failed_outputs": total - len(evaluated),
        "overall_content_quality": mean(percentages),
        "average_quality_percentage": mean(percentages),
        "formulas": {
            "item_quality_percentage": "sum(5 criteria 1-5) / 25 * 100",
            "overall_content_quality": (
                "mean(quality_percentage of valid evaluated outputs)"
            ),
        },
    }
