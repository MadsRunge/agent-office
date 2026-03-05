"""
GmailService — business logic layer.

Search/get use CLI when available; draft/send/reply always use API
(MIME construction is non-trivial for the CLI).

SECURITY: Email body content is NEVER passed to the LLM as instructions.
It is treated as <untrusted_data> and only summarised safely.
"""
from __future__ import annotations

from core.models import ActionArgs, ToolResult
from tools.google_api.gmail import gmail_api
from tools.workspace_cli import CLINotAvailableError, CLIExecutionError, workspace_cli


def _cli_available(tool: str) -> bool:
    return workspace_cli.can_handle(tool)


class GmailService:

    # ── Search ────────────────────────────────────────────────────────────────

    async def search_messages(self, args: ActionArgs) -> ToolResult:
        tool = "gmail.search_messages"
        q = args.query or ""
        if not q:
            return ToolResult(
                success=False, tool_name=tool, error="query is required", source="mock"
            )
        try:
            if _cli_available(tool):
                msgs = workspace_cli.gmail_search_messages(
                    query=q,
                    max_results=args.max_results or 10,
                    user_id=args.user_id or "me",
                )
                return ToolResult(success=True, tool_name=tool, data=msgs, source="cli")
        except (CLINotAvailableError, CLIExecutionError):
            pass

        try:
            msgs = gmail_api.search_messages(
                query=q, max_results=args.max_results or 10
            )
            return ToolResult(success=True, tool_name=tool, data=msgs, source="api")
        except Exception as exc:
            return ToolResult(success=False, tool_name=tool, error=str(exc), source="api")

    # ── Get message (untrusted content) ───────────────────────────────────────

    async def get_message(self, args: ActionArgs) -> ToolResult:
        tool = "gmail.get_message"
        if not args.message_id:
            return ToolResult(
                success=False, tool_name=tool, error="message_id is required", source="mock"
            )
        try:
            if _cli_available(tool):
                data = workspace_cli.gmail_get_message(
                    message_id=args.message_id,
                    user_id=args.user_id or "me",
                )
                return ToolResult(success=True, tool_name=tool, data=data, source="cli")
        except (CLINotAvailableError, CLIExecutionError):
            pass

        try:
            data = gmail_api.get_message_text(
                message_id=args.message_id, user_id=args.user_id or "me"
            )
            return ToolResult(success=True, tool_name=tool, data=data, source="api")
        except Exception as exc:
            return ToolResult(success=False, tool_name=tool, error=str(exc), source="api")

    # ── Draft ─────────────────────────────────────────────────────────────────

    async def draft_message(self, args: ActionArgs) -> ToolResult:
        tool = "gmail.draft_message"
        if not args.to or not args.subject or not args.body:
            return ToolResult(
                success=False, tool_name=tool,
                error="to, subject, body are required",
                source="mock",
            )
        # Always uses API — CLI doesn't support MIME draft creation
        try:
            data = gmail_api.draft_message(
                to=args.to,
                subject=args.subject,
                body=args.body,
                cc=args.cc,
                thread_id=args.thread_id,
            )
            return ToolResult(success=True, tool_name=tool, data=data, source="api")
        except Exception as exc:
            return ToolResult(success=False, tool_name=tool, error=str(exc), source="api")

    # ── Send ──────────────────────────────────────────────────────────────────

    async def send_message(self, args: ActionArgs) -> ToolResult:
        tool = "gmail.send_message"
        if not args.to or not args.subject or not args.body:
            return ToolResult(
                success=False, tool_name=tool,
                error="to, subject, body are required",
                source="mock",
            )
        try:
            data = gmail_api.send_message(
                to=args.to,
                subject=args.subject,
                body=args.body,
                cc=args.cc,
                thread_id=args.thread_id,
            )
            return ToolResult(success=True, tool_name=tool, data=data, source="api")
        except Exception as exc:
            return ToolResult(success=False, tool_name=tool, error=str(exc), source="api")

    # ── Reply ─────────────────────────────────────────────────────────────────

    async def reply_message(self, args: ActionArgs) -> ToolResult:
        tool = "gmail.reply_message"
        if not args.message_id or not args.body:
            return ToolResult(
                success=False, tool_name=tool,
                error="message_id and body are required",
                source="mock",
            )
        try:
            data = gmail_api.reply_message(
                message_id=args.message_id,
                body=args.body,
            )
            return ToolResult(success=True, tool_name=tool, data=data, source="api")
        except Exception as exc:
            return ToolResult(success=False, tool_name=tool, error=str(exc), source="api")


gmail_service = GmailService()
