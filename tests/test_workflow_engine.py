from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine

from src.models.db_models import AgentTask, Workflow, WorkflowStep
from src.workflows.engine import (
    StepStatus,
    WorkflowEngine,
    WorkflowStatus,
    WorkflowType,
)


@pytest.fixture(name="db_engine")
def db_engine_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="session")
def session_fixture(db_engine):
    with Session(db_engine) as s:
        yield s


def _make_workflow(session: Session, workflow_type: str = "full_sdd") -> Workflow:
    workflow = Workflow(
        spec_path="spec.md",
        status=WorkflowStatus.PENDING,
        type=workflow_type,
    )
    session.add(workflow)
    session.commit()
    session.refresh(workflow)
    return workflow


def _make_engine(session: Session) -> WorkflowEngine:
    return WorkflowEngine(
        session=session,
        sandbox_workdir=None,
        max_retries=3,
    )


def _mock_sandbox_success() -> MagicMock:
    mock_sb = MagicMock()
    mock_sb.__enter__ = MagicMock(return_value=mock_sb)
    mock_sb.__exit__ = MagicMock(return_value=False)
    mock_sb.execute = MagicMock(
        return_value={"exit_code": 0, "stdout": "ok", "stderr": ""}
    )
    return mock_sb


def _mock_sandbox_failure(stderr: str = "test failed") -> MagicMock:
    mock_sb = MagicMock()
    mock_sb.__enter__ = MagicMock(return_value=mock_sb)
    mock_sb.__exit__ = MagicMock(return_value=False)
    mock_sb.execute = MagicMock(
        return_value={"exit_code": 1, "stdout": "", "stderr": stderr}
    )
    return mock_sb


class TestWorkflowEngineRun:
    def test_run_unknown_workflow_id_raises(self, session: Session) -> None:
        engine = _make_engine(session)
        with pytest.raises(ValueError, match="not found"):
            engine.run("nonexistent-id")

    def test_run_unsupported_type_marks_failed(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="unknown_type")
        engine = _make_engine(session)
        result = engine.run(workflow.id)
        assert result.status == WorkflowStatus.FAILED

    def test_run_sets_status_to_running_then_completed(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="fix_bug")
        engine = _make_engine(session)

        engine.developer.run = MagicMock(return_value={"code": "fixed code"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "OK"}
        )

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            result = engine.run(workflow.id)

        assert result.status == WorkflowStatus.COMPLETED


class TestFullSddWorkflow:
    def test_full_sdd_success(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="full_sdd")
        engine = _make_engine(session)

        engine.planner.run = MagicMock(return_value={"plan": "step 1: do this"})
        engine.developer.run = MagicMock(return_value={"code": "def foo(): pass"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "LGTM"}
        )
        engine.validator.run = MagicMock(
            return_value={"valid": True, "comments": "Matches spec"}
        )

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            result = engine.run(workflow.id)

        assert result.status == WorkflowStatus.COMPLETED

    def test_full_sdd_creates_expected_steps(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="full_sdd")
        engine = _make_engine(session)

        engine.planner.run = MagicMock(return_value={"plan": "plan content"})
        engine.developer.run = MagicMock(return_value={"code": "code content"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "OK"}
        )
        engine.validator.run = MagicMock(
            return_value={"valid": True, "comments": "OK"}
        )

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            engine.run(workflow.id)

        steps = session.exec(
            __import__("sqlmodel").select(WorkflowStep).where(
                WorkflowStep.workflow_id == workflow.id
            )
        ).all()

        titles = [s.title for s in steps]
        assert "Planning" in titles
        assert "Development" in titles
        assert "Review" in titles

    def test_full_sdd_planner_failure_marks_workflow_failed(
        self, session: Session
    ) -> None:
        workflow = _make_workflow(session, workflow_type="full_sdd")
        engine = _make_engine(session)

        engine.planner.run = MagicMock(side_effect=RuntimeError("LLM unreachable"))

        result = engine.run(workflow.id)
        assert result.status == WorkflowStatus.FAILED

    def test_full_sdd_review_failure_marks_workflow_failed(
        self, session: Session
    ) -> None:
        workflow = _make_workflow(session, workflow_type="full_sdd")
        engine = _make_engine(session)

        engine.planner.run = MagicMock(return_value={"plan": "plan"})
        engine.developer.run = MagicMock(return_value={"code": "code"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": False, "comments": "Bad code"}
        )
        engine.validator.run = MagicMock(
            return_value={"valid": True, "comments": "OK"}
        )

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            result = engine.run(workflow.id)

        assert result.status == WorkflowStatus.FAILED

    def test_full_sdd_validator_failure_marks_workflow_failed(
        self, session: Session
    ) -> None:
        workflow = _make_workflow(session, workflow_type="full_sdd")
        engine = _make_engine(session)

        engine.planner.run = MagicMock(return_value={"plan": "plan"})
        engine.developer.run = MagicMock(return_value={"code": "code"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "OK"}
        )
        engine.validator.run = MagicMock(
            return_value={"valid": False, "comments": "Does not match spec"}
        )

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            result = engine.run(workflow.id)

        assert result.status == WorkflowStatus.FAILED

    def test_full_sdd_developer_retries_on_verification_failure(
        self, session: Session
    ) -> None:
        workflow = _make_workflow(session, workflow_type="full_sdd")
        engine = _make_engine(session)
        engine.max_retries = 3

        engine.planner.run = MagicMock(return_value={"plan": "plan"})
        engine.developer.run = MagicMock(return_value={"code": "code"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "OK"}
        )
        engine.validator.run = MagicMock(
            return_value={"valid": True, "comments": "OK"}
        )

        call_count = 0

        def side_effect_sandbox(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return _mock_sandbox_failure("assertion failed")
            return _mock_sandbox_success()

        with patch(
            "src.workflows.engine.LocalSandbox", side_effect=side_effect_sandbox
        ):
            result = engine.run(workflow.id)

        assert result.status == WorkflowStatus.COMPLETED
        assert engine.developer.run.call_count == 2

    def test_full_sdd_max_retries_exhausted_marks_failed(
        self, session: Session
    ) -> None:
        workflow = _make_workflow(session, workflow_type="full_sdd")
        engine = _make_engine(session)
        engine.max_retries = 2

        engine.planner.run = MagicMock(return_value={"plan": "plan"})
        engine.developer.run = MagicMock(return_value={"code": "bad code"})

        with patch(
            "src.workflows.engine.LocalSandbox",
            return_value=_mock_sandbox_failure("tests failed"),
        ):
            result = engine.run(workflow.id)

        assert result.status == WorkflowStatus.FAILED
        assert engine.developer.run.call_count == 2

    def test_full_sdd_parallel_review_calls_both_agents(
        self, session: Session
    ) -> None:
        workflow = _make_workflow(session, workflow_type="full_sdd")
        engine = _make_engine(session)

        engine.planner.run = MagicMock(return_value={"plan": "plan"})
        engine.developer.run = MagicMock(return_value={"code": "code"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "OK"}
        )
        engine.validator.run = MagicMock(
            return_value={"valid": True, "comments": "OK"}
        )

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            engine.run(workflow.id)

        engine.reviewer.run.assert_called_once()
        engine.validator.run.assert_called_once()


class TestFixBugWorkflow:
    def test_fix_bug_success(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="fix_bug")
        engine = _make_engine(session)

        engine.developer.run = MagicMock(return_value={"code": "fixed code"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "OK"}
        )

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            result = engine.run(workflow.id)

        assert result.status == WorkflowStatus.COMPLETED

    def test_fix_bug_creates_expected_steps(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="fix_bug")
        engine = _make_engine(session)

        engine.developer.run = MagicMock(return_value={"code": "fixed"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "OK"}
        )

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            engine.run(workflow.id)

        steps = session.exec(
            __import__("sqlmodel").select(WorkflowStep).where(
                WorkflowStep.workflow_id == workflow.id
            )
        ).all()

        titles = [s.title for s in steps]
        assert "Bug Fix" in titles
        assert "Review" in titles
        assert "Planning" not in titles

    def test_fix_bug_does_not_call_planner(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="fix_bug")
        engine = _make_engine(session)

        engine.developer.run = MagicMock(return_value={"code": "code"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "OK"}
        )
        engine.planner.run = MagicMock(return_value={"plan": "unreachable"})

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            engine.run(workflow.id)

        engine.planner.run.assert_not_called()

    def test_fix_bug_uses_only_pytest_verification(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="fix_bug")
        engine = _make_engine(session)

        engine.developer.run = MagicMock(return_value={"code": "code"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "OK"}
        )

        mock_sb = _mock_sandbox_success()
        with patch("src.workflows.engine.LocalSandbox", return_value=mock_sb):
            engine.run(workflow.id)

        executed_commands = [call.args[0] for call in mock_sb.execute.call_args_list]
        assert "pytest" in executed_commands
        assert "ruff check ." not in executed_commands

    def test_fix_bug_review_failure_marks_failed(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="fix_bug")
        engine = _make_engine(session)

        engine.developer.run = MagicMock(return_value={"code": "code"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": False, "comments": "Not good"}
        )

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            result = engine.run(workflow.id)

        assert result.status == WorkflowStatus.FAILED


class TestRefactorWorkflow:
    def test_refactor_success(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="refactor")
        engine = _make_engine(session)

        engine.planner.run = MagicMock(return_value={"plan": "refactor plan"})
        engine.developer.run = MagicMock(return_value={"code": "refactored code"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "Clean!"}
        )

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            result = engine.run(workflow.id)

        assert result.status == WorkflowStatus.COMPLETED

    def test_refactor_creates_expected_steps(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="refactor")
        engine = _make_engine(session)

        engine.planner.run = MagicMock(return_value={"plan": "plan"})
        engine.developer.run = MagicMock(return_value={"code": "code"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "OK"}
        )

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            engine.run(workflow.id)

        steps = session.exec(
            __import__("sqlmodel").select(WorkflowStep).where(
                WorkflowStep.workflow_id == workflow.id
            )
        ).all()

        titles = [s.title for s in steps]
        assert "Refactor Planning" in titles
        assert "Refactoring" in titles
        assert "Review" in titles

    def test_refactor_does_not_call_validator(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="refactor")
        engine = _make_engine(session)

        engine.planner.run = MagicMock(return_value={"plan": "plan"})
        engine.developer.run = MagicMock(return_value={"code": "code"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "OK"}
        )
        engine.validator.run = MagicMock(return_value={"valid": True, "comments": "OK"})

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            engine.run(workflow.id)

        engine.validator.run.assert_not_called()


class TestDatabasePersistence:
    def test_agent_tasks_are_persisted(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="fix_bug")
        engine = _make_engine(session)

        engine.developer.run = MagicMock(return_value={"code": "some code"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "OK"}
        )

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            engine.run(workflow.id)

        tasks = session.exec(__import__("sqlmodel").select(AgentTask)).all()
        assert len(tasks) > 0

    def test_completed_steps_have_timestamps(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="fix_bug")
        engine = _make_engine(session)

        engine.developer.run = MagicMock(return_value={"code": "code"})
        engine.reviewer.run = MagicMock(
            return_value={"approved": True, "comments": "OK"}
        )

        with patch(
            "src.workflows.engine.LocalSandbox", return_value=_mock_sandbox_success()
        ):
            engine.run(workflow.id)

        steps = session.exec(
            __import__("sqlmodel").select(WorkflowStep).where(
                WorkflowStep.workflow_id == workflow.id
            )
        ).all()

        for step in steps:
            assert step.started_at is not None
            assert step.completed_at is not None

    def test_failed_step_has_failed_status(self, session: Session) -> None:
        workflow = _make_workflow(session, workflow_type="fix_bug")
        engine = _make_engine(session)
        engine.max_retries = 1

        engine.developer.run = MagicMock(return_value={"code": "code"})

        with patch(
            "src.workflows.engine.LocalSandbox",
            return_value=_mock_sandbox_failure("error"),
        ):
            engine.run(workflow.id)

        steps = session.exec(
            __import__("sqlmodel").select(WorkflowStep).where(
                WorkflowStep.workflow_id == workflow.id
            )
        ).all()

        bug_fix_step = next(s for s in steps if s.title == "Bug Fix")
        assert bug_fix_step.status == StepStatus.FAILED
