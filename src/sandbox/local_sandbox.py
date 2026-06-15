import os
import subprocess
from typing import Any

from src.sandbox.base import BaseSandbox


class LocalSandbox(BaseSandbox):

    def __init__(
        self,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.workdir = workdir
        self.env = env

    def start(self) -> None:
        pass

    def execute(self, command: str, timeout: int = 300) -> dict[str, Any]:
        merged_env = os.environ.copy()
        if self.env:
            merged_env.update(self.env)
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.workdir,
                env=merged_env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired as e:
            stdout_str = ""
            if e.stdout is not None:
                if isinstance(e.stdout, bytes):
                    stdout_str = e.stdout.decode(errors="replace")
                else:
                    stdout_str = str(e.stdout)
            stderr_str = f"Command timed out after {timeout} seconds"
            if e.stderr is not None:
                if isinstance(e.stderr, bytes):
                    stderr_str += f"\n{e.stderr.decode(errors='replace')}"
                else:
                    stderr_str += f"\n{str(e.stderr)}"
            return {
                "stdout": stdout_str,
                "stderr": stderr_str,
                "exit_code": -1,
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
            }

    def stop(self) -> None:
        pass
