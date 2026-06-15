from typing import Any

from src.agents.base import BaseAgent


class ReviewerAgent(BaseAgent):
    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Analyse le code généré sous les aspects qualité et sécurité."""
        code = input_data.get("code", "")
        file_path = input_data.get("file_path", "")
        requirements = input_data.get("requirements", "")

        system_prompt = (
            "You are an expert code reviewer. "
            "Analyze the code for quality and security. "
            "Start your response with exactly 'APPROVED: True' or "
            "'APPROVED: False' on the first line, followed by "
            "'COMMENTS:' and your detailed comments."
        )

        user_prompt = (
            f"File Path:\n{file_path}\n\n"
            f"Requirements:\n{requirements}\n\n"
            f"Code to Review:\n{code}"
        )

        response_text = self._call_llm(system_prompt, user_prompt)

        approved = False
        comments = response_text

        for line in response_text.splitlines():
            if line.strip().upper().startswith("APPROVED:"):
                val = line.split(":", 1)[1].strip().upper()
                if "TRUE" in val:
                    approved = True
                elif "FALSE" in val:
                    approved = False
                break

        if "COMMENTS:" in response_text:
            comments = response_text.split("COMMENTS:", 1)[1].strip()

        return {
            "approved": approved,
            "comments": comments
        }
