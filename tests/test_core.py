from collections.abc import Generator

import pytest
from sqlmodel import Session, SQLModel, create_engine

from src.core.config import Settings
from src.models.db_models import (
    AgentTask,
    RepositoryConfig,
    SandboxSession,
    Workflow,
    WorkflowStep,
)


def test_settings_loading() -> None:
    settings = Settings(DATABASE_URL="sqlite:///:memory:", APP_NAME="Test Platform")
    assert settings.DATABASE_URL == "sqlite:///:memory:"
    assert settings.APP_NAME == "Test Platform"


@pytest.fixture(name="db_session")
def db_session_fixture() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_db_model_relationships(db_session: Session) -> None:
    repo = RepositoryConfig(
        url="https://github.com/example/repo.git",
        local_path="./repos/repo-1",
        branch="main",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    assert repo.id is not None

    workflow = Workflow(
        repo_id=repo.id,
        spec_path="./specs/spec.md",
        status="pending",
        type="full_sdd",
    )
    db_session.add(workflow)
    db_session.commit()
    db_session.refresh(workflow)

    assert workflow.repo_id == repo.id
    assert len(repo.workflows) == 1
    assert repo.workflows[0].id == workflow.id

    step = WorkflowStep(
        workflow_id=workflow.id,
        title="Planning",
        status="inprogress",
        agent_id="planner_v1",
    )
    db_session.add(step)
    db_session.commit()
    db_session.refresh(step)

    assert len(workflow.steps) == 1
    assert workflow.steps[0].id == step.id

    task = AgentTask(
        step_id=step.id,
        prompt="Create a plan",
        response="Plan generated",
        status="success",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    assert len(step.agent_tasks) == 1
    assert step.agent_tasks[0].id == task.id

    session = SandboxSession(
        task_id=task.id,
        container_id="cont-123",
        status="running",
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    assert len(task.sandbox_sessions) == 1
    assert task.sandbox_sessions[0].id == session.id
