import unittest

from server.app.google_workspace import GoogleWorkspaceClient


class GoogleWorkspaceTests(unittest.TestCase):
    def test_forms_filter_uses_utc_zulu_time(self) -> None:
        self.assertEqual(
            GoogleWorkspaceClient._google_timestamp("2026-07-22T01:02:03+00:00"),
            "2026-07-22T01:02:03.000Z",
        )


if __name__ == "__main__":
    unittest.main()
