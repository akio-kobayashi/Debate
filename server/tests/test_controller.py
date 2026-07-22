import unittest

from server.app.theme_context import extract_theme_context


class ThemeContextTests(unittest.TestCase):
    def test_extracts_facilitator_labels(self) -> None:
        text = """\
議題（整理後）：大学の授業で生成AIの使用を認めるべきか
用語の定義：生成AIの使用とは、文章生成と対話による学習支援を指す
対象範囲・前提：大学の通常授業を対象とする
主な評価観点：学習効果、公平性、評価の信頼性
現在の論点：基礎能力の形成とAI利用の両立
次の指示：Aは利用条件を具体化する
"""
        context = extract_theme_context(text)

        self.assertEqual(
            context["motion"],
            "大学の授業で生成AIの使用を認めるべきか",
        )
        self.assertEqual(
            context["current_issue"],
            "基礎能力の形成とAI利用の両立",
        )
        self.assertEqual(
            context["next_instruction"],
            "Aは利用条件を具体化する",
        )

    def test_accepts_ascii_colons_and_markdown_prefixes(self) -> None:
        text = """\
**議題（整理後）**: 学校での生成AI利用
- 現在の論点：学習支援と依存のバランス
"""
        context = extract_theme_context(text)

        self.assertEqual(context["motion"], "学校での生成AI利用")
        self.assertEqual(context["current_issue"], "学習支援と依存のバランス")


if __name__ == "__main__":
    unittest.main()
