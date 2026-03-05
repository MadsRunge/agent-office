"""
DriveService — business logic layer.

list/search use CLI when available; create/upload always use API.
"""
from __future__ import annotations

from core.models import ActionArgs, ToolResult
from tools.google_api.drive import drive_api
from tools.workspace_cli import CLINotAvailableError, CLIExecutionError, workspace_cli


def _cli_available(tool: str) -> bool:
    return workspace_cli.can_handle(tool)


class DriveService:

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_files(self, args: ActionArgs) -> ToolResult:
        tool = "drive.list_files"
        try:
            if _cli_available(tool):
                files = workspace_cli.drive_list_files(
                    query=args.search_query,
                    max_results=args.max_results or 10,
                )
                return ToolResult(success=True, tool_name=tool, data=files, source="cli")
        except (CLINotAvailableError, CLIExecutionError):
            pass

        try:
            files = drive_api.list_files(
                query=args.search_query, max_results=args.max_results or 10
            )
            return ToolResult(success=True, tool_name=tool, data=files, source="api")
        except Exception as exc:
            return ToolResult(success=False, tool_name=tool, error=str(exc), source="api")

    # ── Search ────────────────────────────────────────────────────────────────

    async def search_files(self, args: ActionArgs) -> ToolResult:
        tool = "drive.search_files"
        q = args.search_query or args.file_name or ""
        if not q:
            return ToolResult(
                success=False, tool_name=tool, error="search_query is required", source="mock"
            )
        try:
            if _cli_available(tool):
                files = workspace_cli.drive_list_files(
                    query=f"name contains '{q}' and trashed=false",
                    max_results=args.max_results or 10,
                )
                return ToolResult(success=True, tool_name=tool, data=files, source="cli")
        except (CLINotAvailableError, CLIExecutionError):
            pass

        try:
            files = drive_api.search_files(search_query=q, max_results=args.max_results or 10)
            return ToolResult(success=True, tool_name=tool, data=files, source="api")
        except Exception as exc:
            return ToolResult(success=False, tool_name=tool, error=str(exc), source="api")

    # ── Create folder ─────────────────────────────────────────────────────────

    async def create_folder(self, args: ActionArgs) -> ToolResult:
        tool = "drive.create_folder"
        name = args.folder_name or args.file_name
        if not name:
            return ToolResult(
                success=False, tool_name=tool, error="folder_name is required", source="mock"
            )
        try:
            if _cli_available(tool):
                data = workspace_cli.drive_create_folder(
                    name=name, parent_id=args.parent_id
                )
                return ToolResult(success=True, tool_name=tool, data=data, source="cli")
        except (CLINotAvailableError, CLIExecutionError):
            pass

        try:
            data = drive_api.create_folder(name=name, parent_id=args.parent_id)
            return ToolResult(success=True, tool_name=tool, data=data, source="api")
        except Exception as exc:
            return ToolResult(success=False, tool_name=tool, error=str(exc), source="api")

    # ── Create document ───────────────────────────────────────────────────────

    async def create_document(self, args: ActionArgs) -> ToolResult:
        tool = "drive.create_document"
        name = args.file_name
        if not name:
            return ToolResult(
                success=False, tool_name=tool, error="file_name is required", source="mock"
            )
        # Always uses API — CLI doesn't support Docs creation
        try:
            data = drive_api.create_document(
                name=name,
                content=args.file_content or "",
                parent_id=args.parent_id,
            )
            return ToolResult(success=True, tool_name=tool, data=data, source="api")
        except Exception as exc:
            return ToolResult(success=False, tool_name=tool, error=str(exc), source="api")


drive_service = DriveService()
