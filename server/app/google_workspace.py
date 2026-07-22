from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings


class GoogleWorkspaceError(RuntimeError):
    pass


class GoogleWorkspaceClient:
    """Small, optional Google Forms/Drive adapter.

    Credentials are deliberately read from paths outside the repository. The API
    never accepts credentials in a request body and never logs token contents.
    """

    scopes = (
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/forms.body.readonly",
        "https://www.googleapis.com/auth/forms.responses.readonly",
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.google_form_id
            and self.settings.google_drive_folder_id
            and self.settings.google_oauth_client_secrets
            and self.settings.google_oauth_token
        )

    def _credentials(self) -> Any:
        if not self.configured:
            raise GoogleWorkspaceError(
                "Google integration is not configured; set GOOGLE_FORM_ID, "
                "GOOGLE_DRIVE_FOLDER_ID, GOOGLE_OAUTH_CLIENT_SECRETS, and "
                "GOOGLE_OAUTH_TOKEN"
            )
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
        except ImportError as exc:
            raise GoogleWorkspaceError(
                "Google client libraries are not installed"
            ) from exc

        token_path = Path(self.settings.google_oauth_token).expanduser()
        if not token_path.is_file():
            raise GoogleWorkspaceError(
                f"Google OAuth token file was not found: {token_path}"
            )
        try:
            credentials = Credentials.from_authorized_user_file(
                str(token_path), list(self.scopes)
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise GoogleWorkspaceError("Google OAuth token file is invalid") from exc
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                token_path.write_text(credentials.to_json(), encoding="utf-8")
            except Exception as exc:  # Google auth errors vary by client version.
                raise GoogleWorkspaceError("Google OAuth token refresh failed") from exc
        if not credentials.valid:
            raise GoogleWorkspaceError(
                "Google OAuth token is not valid; authorize the account again"
            )
        if not credentials.has_scopes(list(self.scopes)):
            raise GoogleWorkspaceError(
                "Google OAuth token lacks the required Forms/Drive scopes"
            )
        return credentials

    def _services(self) -> tuple[Any, Any]:
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise GoogleWorkspaceError(
                "Google client libraries are not installed"
            ) from exc
        credentials = self._credentials()
        return (
            build("forms", "v1", credentials=credentials, cache_discovery=False),
            build("drive", "v3", credentials=credentials, cache_discovery=False),
        )

    @staticmethod
    def _google_timestamp(value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )

    def fetch_responses(
        self,
        started_at: str,
        ended_at: str | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        forms, _drive = self._services()
        try:
            form = forms.forms().get(formId=self.settings.google_form_id).execute()
            responses: list[dict[str, Any]] = []
            page_token: str | None = None
            while True:
                request = forms.forms().responses().list(
                    formId=self.settings.google_form_id,
                    filter=f"timestamp > {self._google_timestamp(started_at)}",
                    pageSize=5000,
                    pageToken=page_token,
                )
                payload = request.execute()
                responses.extend(payload.get("responses", []))
                page_token = payload.get("nextPageToken")
                if not page_token:
                    break
        except Exception as exc:
            raise GoogleWorkspaceError("Google Form responses could not be read") from exc

        if ended_at:
            end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            responses = [
                response
                for response in responses
                if datetime.fromisoformat(
                    (response.get("lastSubmittedTime") or response.get("createTime"))
                    .replace("Z", "+00:00")
                )
                <= end
            ]
        return form, responses

    def upload_docx(self, content: bytes, filename: str) -> dict[str, str]:
        try:
            from googleapiclient.http import MediaIoBaseUpload
        except ImportError as exc:
            raise GoogleWorkspaceError(
                "Google client libraries are not installed"
            ) from exc
        import io

        _forms, drive = self._services()
        metadata = {
            "name": filename,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [self.settings.google_drive_folder_id],
        }
        media = MediaIoBaseUpload(
            io.BytesIO(content),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            resumable=False,
        )
        try:
            result = (
                drive.files()
                .create(
                    body=metadata,
                    media_body=media,
                    fields="id,name,mimeType,webViewLink",
                )
                .execute()
            )
        except Exception as exc:
            raise GoogleWorkspaceError("Google Drive upload failed") from exc
        file_id = str(result.get("id", ""))
        if not file_id:
            raise GoogleWorkspaceError("Google Drive returned no file id")
        return {
            "file_id": file_id,
            "name": str(result.get("name", filename)),
            "url": str(result.get("webViewLink") or f"https://drive.google.com/open?id={file_id}"),
        }
