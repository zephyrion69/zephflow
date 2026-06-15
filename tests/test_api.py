from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from src.api.router import router
from src.core.database import get_session
from src.main import app
from src.models.db_models import RepositoryConfig, Workflow
from src.workflows.engine import WorkflowStatus


@pytest.fixture(name="db_engine")
def db_engine_fixture():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="session")
def session_fixture(db_engine) -> Generator[Session, None, None]:
    with Session(db_engine) as s:
        yield s


@pytest.fixture(name="client")
def client_fixture(db_engine) -> Generator[TestClient, None, None]:
    def override_get_session() -> Generator[Session, None, None]:
        with Session(db_engine) as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


class TestHealthEndpoint:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestRepositoryEndpoints:
    def test_create_repository(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/repositories",
            json={
                "url": "https://github.com/example/repo.git",
                "branch": "main",
                "local_path": "./repos/example",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["url"] == "https://github.com/example/repo.git"
        assert data["branch"] == "main"
        assert data["local_path"] == "./repos/example"
        assert "id" in data

    def test_list_repositories_empty(self, client: TestClient) -> None:
        response = client.get("/api/v1/repositories")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_repositories_returns_created(self, client: TestClient) -> None:
        client.post(
            "/api/v1/repositories",
            json={
                "url": "https://github.com/test/repo.git",
                "branch": "main",
                "local_path": "./repos/test",
            },
        )
        response = client.get("/api/v1/repositories")
        assert response.status_code == 200
        repos = response.json()
        assert len(repos) == 1
        assert repos[0]["url"] == "https://github.com/test/repo.git"


class TestWorkflowTriggerEndpoint:
    def test_trigger_workflow_success(self, client: TestClient) -> None:
        with patch("src.api.router._run_workflow_background"):
            response = client.post(
                "/api/v1/workflows/trigger",
                json={
                    "workflow_type": "fix_bug",
                    "spec_file_path": "./specs/feature.md",
                },
            )
        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "fix_bug"
        assert data["spec_path"] == "./specs/feature.md"
        assert data["status"] == WorkflowStatus.PENDING
        assert "id" in data

    def test_trigger_workflow_with_repository_id(
        self, client: TestClient, session: Session
    ) -> None:
        repo = RepositoryConfig(
            url="https://github.com/x/y.git",
            local_path="./repos/y",
            branch="main",
        )
        session.add(repo)
        session.commit()
        session.refresh(repo)

        with patch("src.api.router._run_workflow_background"):
            response = client.post(
                "/api/v1/workflows/trigger",
                json={
                    "repository_id": repo.id,
                    "workflow_type": "full_sdd",
                    "spec_file_path": "./specs/feature.md",
                },
            )
        assert response.status_code == 201
        data = response.json()
        assert data["repo_id"] == repo.id

    def test_trigger_workflow_invalid_type(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/workflows/trigger",
            json={
                "workflow_type": "invalid_type",
                "spec_file_path": "./specs/feature.md",
            },
        )
        assert response.status_code == 422

    def test_trigger_workflow_repository_not_found(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/workflows/trigger",
            json={
                "repository_id": "nonexistent-uuid",
                "workflow_type": "fix_bug",
                "spec_file_path": "./specs/feature.md",
            },
        )
        assert response.status_code == 404

    def test_trigger_all_valid_workflow_types(self, client: TestClient) -> None:
        for wf_type in ("full_sdd", "fix_bug", "refactor"):
            with patch("src.api.router._run_workflow_background"):
                response = client.post(
                    "/api/v1/workflows/trigger",
                    json={
                        "workflow_type": wf_type,
                        "spec_file_path": "./spec.md",
                    },
                )
            assert response.status_code == 201, f"Failed for type '{wf_type}'"


class TestWorkflowStatusEndpoint:
    def test_get_workflow_not_found(self, client: TestClient) -> None:
        response = client.get("/api/v1/workflows/nonexistent-id")
        assert response.status_code == 404

    def test_get_workflow_status(self, client: TestClient, session: Session) -> None:
        workflow = Workflow(
            spec_path="./spec.md",
            status=WorkflowStatus.PENDING,
            type="fix_bug",
        )
        session.add(workflow)
        session.commit()
        session.refresh(workflow)

        response = client.get(f"/api/v1/workflows/{workflow.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == workflow.id
        assert data["status"] == WorkflowStatus.PENDING
        assert data["type"] == "fix_bug"
        assert data["steps"] == []

    def test_get_workflow_status_includes_steps(
        self, client: TestClient, session: Session
    ) -> None:
        from src.models.db_models import WorkflowStep

        workflow = Workflow(
            spec_path="./spec.md",
            status=WorkflowStatus.RUNNING,
            type="full_sdd",
        )
        session.add(workflow)
        session.commit()
        session.refresh(workflow)

        step = WorkflowStep(
            workflow_id=workflow.id,
            title="Planning",
            status="completed",
            agent_id="planner",
        )
        session.add(step)
        session.commit()

        response = client.get(f"/api/v1/workflows/{workflow.id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["steps"]) == 1
        assert data["steps"][0]["title"] == "Planning"
        assert data["steps"][0]["agent_id"] == "planner"


class TestGithubWebhookEndpoint:
    def test_webhook_push_event_creates_workflow(self, client: TestClient) -> None:
        payload = {
            "repository": {
                "clone_url": "https://github.com/test/repo.git",
                "html_url": "https://github.com/test/repo",
            }
        }
        with patch("src.api.router._run_workflow_background"):
            response = client.post(
                "/api/v1/webhooks/github",
                json=payload,
                headers={"X-GitHub-Event": "push"},
            )
        assert response.status_code == 202
        data = response.json()
        assert data["workflow_id"] != ""
        assert "initiated" in data["message"]

    def test_webhook_pull_request_event(self, client: TestClient) -> None:
        payload = {
            "repository": {
                "clone_url": "https://github.com/test/repo.git",
            }
        }
        with patch("src.api.router._run_workflow_background"):
            response = client.post(
                "/api/v1/webhooks/github",
                json=payload,
                headers={"X-GitHub-Event": "pull_request"},
            )
        assert response.status_code == 202

    def test_webhook_unknown_event_ignored(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/webhooks/github",
            json={},
            headers={"X-GitHub-Event": "ping"},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["workflow_id"] == ""
        assert "ignored" in data["message"]

    def test_webhook_invalid_signature_rejected(self, client: TestClient) -> None:
        with patch("src.api.router._verify_github_signature", return_value=False):
            response = client.post(
                "/api/v1/webhooks/github",
                json={"repository": {}},
                headers={
                    "X-GitHub-Event": "push",
                    "X-Hub-Signature-256": "sha256=invalidsignature",
                },
            )
        assert response.status_code == 401
