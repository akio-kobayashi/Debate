import unittest

from server.app.prompts import build_messages, build_reference_messages
from server.app.state import DebateSession, TURN_PLAN
from server.app.theme_context import extract_theme_context


class PromptMarkdownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = DebateSession(theme="大学の授業で生成AIを認めるべきか")

    def test_debate_prompts_require_limited_markdown(self) -> None:
        messages = build_messages(self.session, "A", "opening")
        system = messages[0]["content"]
        user = messages[1]["content"]

        self.assertIn("画面表示用のMarkdown", system)
        self.assertIn("Markdownの表、HTMLタグ、XML、JSON", system)
        self.assertIn("### 主張", user)

    def test_define_prompt_keeps_theme_context_labels(self) -> None:
        messages = build_messages(self.session, "C", "define")
        user = messages[1]["content"]

        for label in (
            "### 議題（整理後）：",
            "### 用語の定義：",
            "### 現在の論点：",
            "### 次の指示：",
        ):
            self.assertIn(label, user)

    def test_markdown_define_labels_remain_extractable(self) -> None:
        text = """### 議題（整理後）：生成AI利用の是非
### 用語の定義：授業内の文章生成を指す
### 現在の論点：学習効果と依存のバランス
### 次の指示：Aは利用条件を示す
"""
        context = extract_theme_context(text)

        self.assertEqual(context["motion"], "生成AI利用の是非")
        self.assertEqual(context["current_issue"], "学習効果と依存のバランス")
        self.assertEqual(context["next_instruction"], "Aは利用条件を示す")

    def test_reference_prompt_remains_json_only(self) -> None:
        messages = build_reference_messages(self.session)
        system = messages[0]["content"]

        self.assertIn("必ずJSONオブジェクトだけ", system)
        self.assertIn("Markdownのコードブロックは禁止", system)

    def test_turn_plan_reconciles_after_both_rebuttals(self) -> None:
        self.assertEqual(len(TURN_PLAN), 10)
        self.assertEqual(TURN_PLAN[5], ("B", "rebuttal"))
        self.assertEqual(TURN_PLAN[6], ("C", "reconcile"))
        self.assertEqual(TURN_PLAN[7], ("A", "closing"))

        messages = build_messages(self.session, "C", "reconcile")
        self.assertIn("### Aの反論への応答状況", messages[1]["content"])
        self.assertIn("### 未解決の点", messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
