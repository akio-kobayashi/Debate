from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def form_questions(form: dict[str, Any]) -> dict[str, str]:
    """Return the Forms API question-id to title mapping."""
    result: dict[str, str] = {}
    for item in form.get("items", []):
        question = item.get("questionItem", {}).get("question", {})
        question_id = question.get("questionId")
        title = str(item.get("title", "")).strip()
        if question_id and title:
            result[str(question_id)] = title
    return result


def response_answers(response: dict[str, Any], questions: dict[str, str]) -> dict[str, str]:
    """Flatten single-choice and scale answers without retaining respondent data."""
    result: dict[str, str] = {}
    for question_id, answer in response.get("answers", {}).items():
        title = questions.get(str(question_id))
        if not title:
            continue
        text_answers = answer.get("textAnswers", {}).get("answers", [])
        values = [str(item.get("value", "")).strip() for item in text_answers]
        values = [value for value in values if value]
        if values:
            result[title] = " / ".join(values)
    return result


def normalize_responses(
    form: dict[str, Any],
    responses: list[dict[str, Any]],
    started_at: str,
    ended_at: str | None = None,
) -> list[dict[str, Any]]:
    questions = form_questions(form)
    start = _parse_time(started_at)
    end = _parse_time(ended_at)
    normalized: list[dict[str, Any]] = []
    for response in responses:
        submitted_at = response.get("lastSubmittedTime") or response.get("createTime")
        submitted = _parse_time(submitted_at)
        if start and submitted and submitted <= start:
            continue
        if end and submitted and submitted > end:
            continue
        normalized.append(
            {
                "submitted_at": submitted_at,
                "answers": response_answers(response, questions),
            }
        )
    return normalized


def _distribution(values: list[str]) -> list[dict[str, Any]]:
    counts = Counter(value for value in values if value)
    total = sum(counts.values())
    return [
        {
            "value": value,
            "count": count,
            "percentage": round((count / total) * 100, 1) if total else 0.0,
        }
        for value, count in counts.most_common()
    ]


def aggregate_responses(responses: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute auditable aggregates. Raw answers and respondent identities are omitted."""
    question_values: dict[str, list[str]] = {}
    for response in responses:
        for question, value in response.get("answers", {}).items():
            question_values.setdefault(question, []).append(value)

    distributions = [
        {
            "question": question,
            "answered": len(values),
            "distribution": _distribution(values),
        }
        for question, values in question_values.items()
    ]
    return {
        "respondent_count": len(responses),
        "questions": distributions,
    }
