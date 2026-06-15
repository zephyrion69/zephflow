from typing import Any

from src.agents.base import BaseAgent


class DeveloperAgent(BaseAgent):
    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Génère ou modifie le code source."""
        requirements = input_data.get("requirements", "")
        plan = input_data.get("plan", "")
        file_path = input_data.get("file_path", "")
        current_content = input_data.get("current_content", "")
        feedback = input_data.get("feedback", "")

        system_prompt = (
            "You are an expert software developer. "
            "Your task is to write or modify code based on "
            "the requirements and plan. "
            "You must output ONLY the complete source code, "
            "without markdown formatting or code blocks."
        )

        user_prompt = (
            f"Requirements:\n{requirements}\n\n"
            f"Plan:\n{plan}\n\n"
            f"File Path to implement/modify:\n{file_path}\n\n"
            f"Current Content of {file_path}:\n{current_content}\n\n"
            f"Feedback / Compiler / Test Error Logs to address:\n{feedback}"
        )

        generated_code = self._call_llm(system_prompt, user_prompt)

        return {
            "code": generated_code
        }
