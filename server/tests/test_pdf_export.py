import importlib.util
import io
import unittest


REPORTLAB_AVAILABLE = importlib.util.find_spec("reportlab") is not None


class PdfExportTests(unittest.TestCase):
    @unittest.skipUnless(REPORTLAB_AVAILABLE, "reportlab is required for PDF export")
    def test_markdown_debate_result_is_a_pdf(self) -> None:
        from pypdf import PdfReader

        from server.app.pdf_export import build_debate_pdf

        payload = {
            "theme": "大学の授業で生成AIの使用を認めるべきである",
            "theme_context": {
                "current_issue": "学習効果と公平性の両立",
                "next_instruction": "同意点と追加条件を話し合う",
            },
            "messages": [
                {
                    "speaker": "C",
                    "turn_index": 9,
                    "kind": "summary",
                    "text": "### 合意できる点\n- 利用方法の指導が必要",
                },
                {
                    "speaker": "A",
                    "turn_index": 7,
                    "kind": "closing",
                    "text": "利用を認めるべきです。",
                },
                {
                    "speaker": "B",
                    "turn_index": 8,
                    "kind": "closing",
                    "text": "慎重な制限が必要です。",
                },
            ],
        }

        pdf = build_debate_pdf(payload)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertEqual(len(PdfReader(io.BytesIO(pdf)).pages), 3)


if __name__ == "__main__":
    unittest.main()
