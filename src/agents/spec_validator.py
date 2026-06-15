from typing import Any

from src.agents.base import BaseAgent


class SpecValidatorAgent(BaseAgent):
    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Valide la conformité du code vis-à-vis du PRD."""
        code = input_data.get("code", "")
        requirements = input_data.get("requirements", "")
        file_path = input_data.get("file_path", "")

        system_prompt = (
            "You are an expert QA and validation engineer. "
            "Verify that the provided code is in strict conformity "
            "with requirements. Start with exactly 'VALID: True' "
            "or 'VALID: False' on the first line, followed by "
            "'COMMENTS:' and your validation notes."
        )

        user_prompt = (
            f"File Path:\n{file_path}\n\n"
            f"Requirements:\n{requirements}\n\n"
            f"Code to Validate:\n{code}"
        )

        response_text = self._call_llm(system_prompt, user_prompt)

        valid = False
        comments = response_text

        for line in response_text.splitlines():
            if line.strip().upper().startswith("VALID:"):
                val = line.split(":", 1)[1].strip().upper()
                if "TRUE" in val:
                    valid = True
                elif "FALSE" in val:
                    valid = False
                break

        if "COMMENTS:" in response_text:
            comments = response_text.split("COMMENTS:", 1)[1].strip()

        return {
            "valid": valid,
            "comments": comments
        }
