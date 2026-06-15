import concurrent.futures
import os
from typing import Any

from src.sandbox.base import BaseSandbox

try:
    from docker.models.containers import Container
except ImportError:
    class Container:  # type: ignore
        id: str


DOCKER_TIMEOUT_EXIT_CODE = 124


class DockerSandbox(BaseSandbox):

    def __init__(
        self,
        image: str = "python:3.11-slim",
        workdir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.image = image
        self.workdir = workdir
        self.env = env
        self.client: Any = None
        self.container: Container | None = None
        self.container_id: str | None = None

    def start(self) -> None:
        try:
            import docker
        except ImportError:
            raise ImportError("The 'docker' library is not installed.")
        try:
            self.client = docker.from_env()
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Docker client: {e}")

        volumes = {}
        container_workdir = None
        if self.workdir:
            abs_workdir = os.path.abspath(self.workdir)
            volumes[abs_workdir] = {"bind": "/workspace", "mode": "rw"}
            container_workdir = "/workspace"

        try:
            self.container = self.client.containers.run(
                self.image,
                command="tail -f /dev/null",
                detach=True,
                volumes=volumes,
                working_dir=container_workdir,
                environment=self.env,
            )
            if self.container:
                self.container_id = self.container.id
        except Exception as e:
            raise RuntimeError(f"Failed to start Docker container: {e}")

    def execute(self, command: str, timeout: int = 300) -> dict[str, Any]:
        if not self.container:
            raise RuntimeError("Sandbox is not started.")

        cmd = ["sh", "-c", f"timeout {timeout} {command}"]

        def run_exec() -> Any:
            assert self.container is not None
            return self.container.exec_run(
                cmd,
                demux=True,
                environment=self.env,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_exec)
            try:
                result = future.result(timeout=timeout + 5)
                exit_code, output = result
                stdout_bytes, stderr_bytes = output if output else (None, None)
                stdout = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
                stderr = stderr_bytes.decode(errors="replace") if stderr_bytes else ""
                if exit_code == DOCKER_TIMEOUT_EXIT_CODE:
                    stderr = f"Command timed out after {timeout} seconds\n" + stderr
                    exit_code = -1
                return {
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                }
            except concurrent.futures.TimeoutError:
                try:
                    self.container.kill()
                except Exception:
                    pass
                return {
                    "stdout": "",
                    "stderr": f"Command timed out after {timeout} seconds",
                    "exit_code": -1,
                }
            except Exception as e:
                return {
                    "stdout": "",
                    "stderr": str(e),
                    "exit_code": -1,
                }

    def stop(self) -> None:
        if self.container:
            try:
                self.container.stop(timeout=2)
            except Exception:
                pass
            try:
                self.container.remove(force=True)
            except Exception:
                pass
            self.container = None
            self.container_id = None
