import unittest

from server.app.survey import aggregate_responses, normalize_responses


class SurveyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.form = {
            "items": [
                {
                    "title": "AとBのどちらの立場が説得的でしたか。",
                    "questionItem": {"question": {"questionId": "q1"}},
                },
                {
                    "title": "自信度",
                    "questionItem": {"question": {"questionId": "q2"}},
                },
            ]
        }

    def test_normalizes_responses_and_applies_time_window(self) -> None:
        responses = [
            {
                "responseId": "old",
                "lastSubmittedTime": "2026-07-22T00:00:00Z",
                "answers": {"q1": {"textAnswers": {"answers": [{"value": "A"}]}}},
            },
            {
                "responseId": "current",
                "lastSubmittedTime": "2026-07-22T01:00:00Z",
                "answers": {
                    "q1": {"textAnswers": {"answers": [{"value": "B"}]}},
                    "q2": {"textAnswers": {"answers": [{"value": "4"}]}},
                },
            },
        ]

        normalized = normalize_responses(
            self.form,
            responses,
            "2026-07-22T00:30:00Z",
            "2026-07-22T01:30:00Z",
        )

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["answers"]["自信度"], "4")

    def test_aggregate_contains_counts_and_percentages_only(self) -> None:
        result = aggregate_responses(
            [
                {"answers": {"判断": "A", "自信度": "4"}},
                {"answers": {"判断": "B", "自信度": "4"}},
                {"answers": {"判断": "A", "自信度": "3"}},
            ]
        )

        self.assertEqual(result["respondent_count"], 3)
        judgment = next(item for item in result["questions"] if item["question"] == "判断")
        self.assertEqual(judgment["distribution"][0], {"value": "A", "count": 2, "percentage": 66.7})
        self.assertNotIn("responseId", result)


if __name__ == "__main__":
    unittest.main()
