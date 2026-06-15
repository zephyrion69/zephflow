from typing import Any

from src.agents.base import BaseAgent


class PlannerAgent(BaseAgent):
    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Génère un plan d'implémentation détaillé."""
        requirements = input_data.get("requirements", "")
        code_context = input_data.get("code_context", "")

        system_prompt = (
            "You are a professional software architect and planner. "
            "Your task is to analyze requirements to produce a detailed, "
            "structured implementation plan in Markdown. "
            "The plan must break down work into sequential tasks with "
            "verification steps."
        )

        user_prompt = (
            f"Requirements:\n{requirements}\n\n"
            f"Codebase Context:\n{code_context}"
        )

        plan_content = self._call_llm(system_prompt, user_prompt)

        return {
            "plan": plan_content
        }
