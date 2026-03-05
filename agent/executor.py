"""
Executor — validates and runs an ActionPlan, collecting ToolResults.

In dry-run mode, all tools return mock results without touching Google APIs.
"""
from __future__ import annotations

import time

import structlog

from core.models import ActionPlan, ExecutionResult, ToolResult
from tools.registry import registry, ToolNotFoundError

logger = structlog.get_logger()


class Executor:

    async def run(self, plan: ActionPlan) -> ExecutionResult:
        """Execute all actions in a plan sequentially."""
        if plan.dry_run:
            return self._dry_run_result(plan)

        results: list[ToolResult] = []
        errors: list[str] = []
        citations: list[str] = []
        t0 = time.monotonic()

        for action in plan.actions:
            logger.info("executing_tool", tool=action.tool, args=action.args.model_dump(exclude_none=True))
            try:
                result = await registry.execute(action.tool, action.args.model_dump(exclude_none=True))
            except ToolNotFoundError as exc:
                result = ToolResult(
                    success=False,
                    tool_name=action.tool,
                    error=str(exc),
                    source="mock",
                )
            results.append(result)
            if result.success:
                citations.append(self._citation(action.tool, result))
            else:
                errors.append(f"{action.tool}: {result.error}")

        duration_ms = (time.monotonic() - t0) * 1000
        summary = self._build_summary(plan, results, errors)

        logger.info(
            "execution_complete",
            intent=plan.intent,
            tools=[a.tool for a in plan.actions],
            success_count=sum(1 for r in results if r.success),
            error_count=len(errors),
            duration_ms=round(duration_ms, 1),
        )
        return ExecutionResult(
            plan=plan,
            results=results,
            summary=summary,
            citations=citations,
            errors=errors,
        )

    def _dry_run_result(self, plan: ActionPlan) -> ExecutionResult:
        mock_results = [
            ToolResult(
                success=True,
                tool_name=action.tool,
                data={"dry_run": True, "args": action.args.model_dump(exclude_none=True)},
                source="mock",
            )
            for action in plan.actions
        ]
        actions_str = "\n".join(
            f"  • {a.tool}: {a.args.model_dump(exclude_none=True)}"
            for a in plan.actions
        )
        summary = (
            f"*[DRY RUN]* Would execute {len(plan.actions)} action(s) for: "
            f"{plan.user_message_summary}\n{actions_str}"
        )
        return ExecutionResult(
            plan=plan,
            results=mock_results,
            summary=summary,
            citations=["(dry run — no changes made)"],
            errors=[],
        )

    @staticmethod
    def _citation(tool_name: str, result: ToolResult) -> str:
        """Build a human-readable citation for what was touched."""
        data = result.data or {}
        src = f"[via {result.source}]"

        if tool_name == "calendar.create_event":
            title = data.get("summary", "event")
            link = data.get("htmlLink", "")
            return f"Created calendar event '{title}' {src} {link}".strip()

        if tool_name == "calendar.delete_event":
            return f"Deleted calendar event {src}"

        if tool_name == "calendar.update_event":
            title = data.get("summary", "event")
            return f"Updated calendar event '{title}' {src}"

        if tool_name == "calendar.list_events":
            count = len(data) if isinstance(data, list) else 0
            return f"Listed {count} calendar event(s) {src}"

        if tool_name in ("gmail.send_message", "gmail.reply_message"):
            msg_id = data.get("id", "")
            return f"Sent email (message id: {msg_id}) {src}"

        if tool_name == "gmail.draft_message":
            draft_id = data.get("id", "")
            return f"Created draft (id: {draft_id}) {src}"

        if tool_name == "gmail.search_messages":
            count = len(data) if isinstance(data, list) else 0
            return f"Found {count} email(s) {src}"

        if tool_name in ("drive.list_files", "drive.search_files"):
            count = len(data) if isinstance(data, list) else 0
            return f"Found {count} Drive file(s) {src}"

        if tool_name == "drive.create_folder":
            name = data.get("name", "folder")
            link = data.get("webViewLink", "")
            return f"Created Drive folder '{name}' {src} {link}".strip()

        if tool_name == "drive.create_document":
            name = data.get("name", "document")
            link = data.get("webViewLink", "")
            return f"Created Google Doc '{name}' {src} {link}".strip()

        return f"Executed {tool_name} {src}"

    @staticmethod
    def _build_summary(
        plan: ActionPlan,
        results: list[ToolResult],
        errors: list[str],
    ) -> str:
        succeeded = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if not failed:
            return f"✅ Completed: {plan.user_message_summary}"

        if not succeeded:
            return f"❌ Failed: {plan.user_message_summary}\nErrors: {'; '.join(errors)}"

        return (
            f"⚠️ Partially completed: {plan.user_message_summary}\n"
            f"{len(succeeded)}/{len(results)} actions succeeded.\n"
            f"Errors: {'; '.join(errors)}"
        )


# Singleton
executor = Executor()
