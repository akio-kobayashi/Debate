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
                "current_issue": "CURRENT_ISSUE_SHOULD_NOT_APPEAR",
            },
            "messages": [
                {
                    "speaker": "A",
                    "turn_index": 7,
                    "kind": "closing",
                    "text": "A_ONLY_SHOULD_NOT_APPEAR",
                },
                {
                    "speaker": "B",
                    "turn_index": 8,
                    "kind": "closing",
                    "text": "B_ONLY_SHOULD_NOT_APPEAR",
                },
                {
                    "speaker": "C",
                    "turn_index": 9,
                    "kind": "summary",
                    "text": "### Cの最終整理\n- C_SUMMARY_ONLY",
                },
            ],
        }

        pdf = build_debate_pdf(payload)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        reader = PdfReader(io.BytesIO(pdf))
        self.assertEqual(len(reader.pages), 1)
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("C_SUMMARY_ONLY", extracted)
        self.assertNotIn("A_ONLY_SHOULD_NOT_APPEAR", extracted)
        self.assertNotIn("B_ONLY_SHOULD_NOT_APPEAR", extracted)
        self.assertNotIn("CURRENT_ISSUE_SHOULD_NOT_APPEAR", extracted)


if __name__ == "__main__":
    unittest.main()
