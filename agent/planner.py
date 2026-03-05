"""
Planner — converts a user message into a validated ActionPlan via OpenAI tool-use.

Uses OpenAI's function-calling feature to guarantee structured JSON output.
The model is constrained to call `create_action_plan` exactly once.
"""
from __future__ import annotations

import json
import os

import openai
import structlog

from agent.prompts import ACTION_PLAN_TOOL, get_planner_system_prompt
from core.models import Action, ActionArgs, ActionPlan
from core.policies import plan_requires_confirmation, risk_for_plan
from core.security import sanitize_user_input, has_injection_pattern

logger = structlog.get_logger()

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


class PlannerError(RuntimeError):
    pass


class Planner:
    def __init__(self) -> None:
        self._client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    async def plan(
        self,
        user_message: str,
        timezone: str = "Europe/Copenhagen",
        dry_run: bool = False,
    ) -> ActionPlan:
        """
        Parse user_message into a validated ActionPlan.

        Returns a plan with `follow_up_question` set if required info is missing.
        Raises PlannerError on LLM or validation failures.
        """
        # Sanitise input — only user messages, never external content
        clean = sanitize_user_input(user_message)
        if has_injection_pattern(clean):
            logger.warning("injection_pattern_detected", snippet=clean[:100])
            # Still process — the LLM system prompt constrains behaviour,
            # but we log the warning for audit purposes.

        logger.info("planning", message_preview=clean[:80])

        try:
            response = self._client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": get_planner_system_prompt(timezone)},
                    {"role": "user", "content": clean},
                ],
                tools=[ACTION_PLAN_TOOL],
                tool_choice={"type": "function", "function": {"name": "create_action_plan"}},
            )
        except openai.APIError as exc:
            raise PlannerError(f"OpenAI API error: {exc}") from exc

        # Extract tool-use result
        tool_call = None
        msg = response.choices[0].message
        if msg.tool_calls:
            tc = msg.tool_calls[0]
            if tc.function.name == "create_action_plan":
                tool_call = json.loads(tc.function.arguments)

        if not tool_call:
            raise PlannerError("OpenAI did not return a valid action plan tool call")

        plan = self._parse_plan(tool_call, dry_run=dry_run)
        logger.info(
            "plan_created",
            intent=plan.intent,
            actions=[a.tool for a in plan.actions],
            requires_confirmation=plan.requires_confirmation,
            risk_level=plan.risk_level,
        )
        return plan

    def _parse_plan(self, raw: dict, dry_run: bool = False) -> ActionPlan:
        """Validate and construct an ActionPlan from the LLM's raw tool input."""
        try:
            actions = [
                Action(tool=a["tool"], args=ActionArgs(**a.get("args", {})))
                for a in raw.get("actions", [])
            ]
        except Exception as exc:
            raise PlannerError(f"Failed to parse actions: {exc}") from exc

        if not actions:
            raise PlannerError("Plan contains no actions")

        tool_names = [a.tool for a in actions]

        # Override confirmation/risk using policy (LLM suggestions are advisory)
        requires_conf = (
            raw.get("requires_confirmation", False)
            or plan_requires_confirmation(tool_names)
        )
        risk = risk_for_plan(tool_names)
        # Take the max of LLM suggestion and policy
        risk_order = {"low": 0, "medium": 1, "high": 2}
        llm_risk = raw.get("risk_level", "low")
        if risk_order.get(llm_risk, 0) > risk_order.get(risk, 0):
            risk = llm_risk  # type: ignore[assignment]

        plan = ActionPlan(
            intent=raw.get("intent", "unknown"),
            requires_confirmation=requires_conf,
            actions=actions,
            user_message_summary=raw.get("user_message_summary", ""),
            risk_level=risk,
            follow_up_question=raw.get("follow_up_question"),
            dry_run=dry_run,
        )

        if not plan.is_valid():
            raise PlannerError(
                f"Plan contains tools with unknown namespaces: "
                f"{[a.tool for a in plan.actions]}"
            )
        return plan


# Singleton
planner = Planner()
