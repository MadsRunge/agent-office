"""Google Drive API adapter (handles create/upload — always uses API)."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from tools.google_api.auth import google_auth

FOLDER_MIME = "application/vnd.google-apps.folder"
GDOC_MIME = "application/vnd.google-apps.document"


def _service():
    creds = google_auth.get_credentials()
    if not creds:
        raise RuntimeError("Google account not authenticated. Visit /auth/google")
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _docs_service():
    creds = google_auth.get_credentials()
    if not creds:
        raise RuntimeError("Google account not authenticated. Visit /auth/google")
    return build("docs", "v1", credentials=creds, cache_discovery=False)


class DriveAPIAdapter:
    """Direct Google Drive (and Docs) API calls."""

    def list_files(
        self,
        query: str | None = None,
        max_results: int = 10,
    ) -> list[dict]:
        svc = _service()
        kwargs: dict[str, Any] = {
            "pageSize": max_results,
            "fields": "files(id,name,mimeType,modifiedTime,webViewLink,size)",
        }
        if query:
            kwargs["q"] = query
        resp = svc.files().list(**kwargs).execute()
        return resp.get("files", [])

    def search_files(self, search_query: str, max_results: int = 10) -> list[dict]:
        q = f"name contains '{search_query}' and trashed=false"
        return self.list_files(query=q, max_results=max_results)

    def create_folder(self, name: str, parent_id: str | None = None) -> dict:
        svc = _service()
        meta: dict[str, Any] = {"name": name, "mimeType": FOLDER_MIME}
        if parent_id:
            meta["parents"] = [parent_id]
        return svc.files().create(
            body=meta, fields="id,name,webViewLink"
        ).execute()

    def create_document(self, name: str, content: str = "", parent_id: str | None = None) -> dict:
        """Create a Google Doc and optionally insert text content."""
        svc = _service()
        meta: dict[str, Any] = {"name": name, "mimeType": GDOC_MIME}
        if parent_id:
            meta["parents"] = [parent_id]
        doc = svc.files().create(body=meta, fields="id,name,webViewLink").execute()

        if content:
            docs_svc = _docs_service()
            docs_svc.documents().batchUpdate(
                documentId=doc["id"],
                body={
                    "requests": [
                        {
                            "insertText": {
                                "location": {"index": 1},
                                "text": content,
                            }
                        }
                    ]
                },
            ).execute()
        return doc

    def get_file_metadata(self, file_id: str) -> dict:
        svc = _service()
        return svc.files().get(
            fileId=file_id,
            fields="id,name,mimeType,modifiedTime,webViewLink",
        ).execute()


drive_api = DriveAPIAdapter()
