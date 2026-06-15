import concurrent.futures
from unittest.mock import MagicMock, patch

from src.sandbox.docker_sandbox import DockerSandbox
from src.sandbox.local_sandbox import LocalSandbox


def test_local_sandbox_execution() -> None:
    expected_exit_code = 42
    cmd = (
        "python -c \"import sys; print('hello'); "
        "print('error', file=sys.stderr); sys.exit(42)\""
    )
    with LocalSandbox() as sandbox:
        res = sandbox.execute(cmd)
        assert "hello" in res["stdout"]
        assert "error" in res["stderr"]
        assert res["exit_code"] == expected_exit_code


def test_local_sandbox_timeout() -> None:
    with LocalSandbox() as sandbox:
        cmd = 'python -c "import time; time.sleep(5)"'
        res = sandbox.execute(cmd, timeout=1)
        assert res["exit_code"] == -1
        assert "timed out" in res["stderr"]


def test_local_sandbox_workdir_and_env() -> None:
    with LocalSandbox(workdir=".", env={"TEST_VAR": "value123"}) as sandbox:
        cmd = "python -c \"import os; print(os.environ.get('TEST_VAR', ''))\""
        res = sandbox.execute(cmd)
        assert "value123" in res["stdout"]
        assert res["exit_code"] == 0


def test_docker_sandbox_success() -> None:
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "mock_container_id_123"
    mock_container.exec_run.return_value = (0, (b"hello_docker", b"error_docker"))
    mock_client.containers.run.return_value = mock_container

    with patch("docker.from_env", return_value=mock_client):
        with DockerSandbox(workdir=".", env={"TEST_VAR": "abc"}) as sandbox:
            assert sandbox.container is not None
            assert sandbox.container_id == "mock_container_id_123"
            res = sandbox.execute("echo hello")
            assert res["exit_code"] == 0
            assert res["stdout"] == "hello_docker"
            assert res["stderr"] == "error_docker"

        mock_container.stop.assert_called_once_with(timeout=2)
        mock_container.remove.assert_called_once_with(force=True)


def test_docker_sandbox_timeout_exit_code() -> None:
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.exec_run.return_value = (124, (b"", b"some error"))
    mock_client.containers.run.return_value = mock_container

    with patch("docker.from_env", return_value=mock_client):
        with DockerSandbox() as sandbox:
            res = sandbox.execute("sleep 10", timeout=1)
            assert res["exit_code"] == -1
            assert "timed out" in res["stderr"]


@patch("concurrent.futures.ThreadPoolExecutor.submit")
def test_docker_sandbox_thread_timeout(mock_submit: MagicMock) -> None:
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_client.containers.run.return_value = mock_container

    mock_future = MagicMock()
    mock_future.result.side_effect = concurrent.futures.TimeoutError()
    mock_submit.return_value = mock_future

    with patch("docker.from_env", return_value=mock_client):
        with DockerSandbox() as sandbox:
            res = sandbox.execute("sleep 10", timeout=1)
            assert res["exit_code"] == -1
            assert "timed out" in res["stderr"]


def test_docker_sandbox_exceptions() -> None:
    mock_client = MagicMock()
    mock_client.containers.run.side_effect = Exception("Docker run error")

    with patch("docker.from_env", return_value=mock_client):
        sandbox = DockerSandbox()
        try:
            sandbox.start()
            assert False
        except Exception as e:
            assert "Failed to start Docker container" in str(e)
