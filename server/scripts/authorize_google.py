#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/forms.body.readonly",
    "https://www.googleapis.com/auth/forms.responses.readonly",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorize Debate Demo Google access")
    parser.add_argument("--credentials", required=True, help="OAuth client JSON path")
    parser.add_argument("--token", required=True, help="Output token JSON path")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(args.credentials, SCOPES)
    credentials = flow.run_local_server(
        host="127.0.0.1",
        port=args.port,
        open_browser=not args.no_browser,
        authorization_prompt_message="Open this URL in the browser: {url}",
    )
    token_path = Path(args.token).expanduser()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    token_path.chmod(0o600)
    print(f"Google authorization saved to {token_path}")


if __name__ == "__main__":
    main()
