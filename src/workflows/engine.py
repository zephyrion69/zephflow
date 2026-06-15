import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from enum import Enum
from typing import Any

from sqlmodel import Session

from src.agents.developer import DeveloperAgent
from src.agents.planner import PlannerAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.spec_validator import SpecValidatorAgent
from src.models.db_models import AgentTask, Workflow, WorkflowStep
from src.sandbox.local_sandbox import LocalSandbox

logger = logging.getLogger(__name__)

MAX_FEEDBACK_ITERATIONS = 3


class WorkflowType(str, Enum):
    FULL_SDD = "full_sdd"
    FIX_BUG = "fix_bug"
    REFACTOR = "refactor"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowEngine:
    def __init__(
        self,
        session: Session,
        planner_model: str = "gpt-4",
        developer_model: str = "gpt-4",
        reviewer_model: str = "gpt-4",
        validator_model: str = "gpt-4",
        sandbox_workdir: str | None = None,
        max_retries: int = MAX_FEEDBACK_ITERATIONS,
    ) -> None:
        self.session = session
        self.planner = PlannerAgent(model_name=planner_model)
        self.developer = DeveloperAgent(model_name=developer_model)
        self.reviewer = ReviewerAgent(model_name=reviewer_model)
        self.validator = SpecValidatorAgent(model_name=validator_model)
        self.sandbox_workdir = sandbox_workdir
        self.max_retries = max_retries

    def run(self, workflow_id: str) -> Workflow:
        workflow = self.session.get(Workflow, workflow_id)
        if workflow is None:
            raise ValueError(f"Workflow {workflow_id!r} not found.")

        workflow.status = WorkflowStatus.RUNNING
        self.session.add(workflow)
        self.session.commit()
        self.session.refresh(workflow)

        try:
            if workflow.type == WorkflowType.FULL_SDD:
                self._run_full_sdd(workflow)
            elif workflow.type == WorkflowType.FIX_BUG:
                self._run_fix_bug(workflow)
            elif workflow.type == WorkflowType.REFACTOR:
                self._run_refactor(workflow)
            else:
                raise ValueError(f"Unsupported workflow type: {workflow.type!r}")
            workflow.status = WorkflowStatus.COMPLETED
        except Exception as exc:
            logger.exception("Workflow %s failed: %s", workflow_id, exc)
            workflow.status = WorkflowStatus.FAILED

        self.session.add(workflow)
        self.session.commit()
        self.session.refresh(workflow)
        return workflow

    def _create_step(self, workflow_id: str, title: str, agent_id: str) -> WorkflowStep:
        step = WorkflowStep(
            workflow_id=workflow_id,
            title=title,
            status=StepStatus.PENDING,
            agent_id=agent_id,
        )
        self.session.add(step)
        self.session.commit()
        self.session.refresh(step)
        return step

    def _start_step(self, step: WorkflowStep) -> None:
        step.status = StepStatus.RUNNING
        step.started_at = datetime.utcnow()
        self.session.add(step)
        self.session.commit()

    def _complete_step(self, step: WorkflowStep, success: bool = True) -> None:
        step.status = StepStatus.COMPLETED if success else StepStatus.FAILED
        step.completed_at = datetime.utcnow()
        self.session.add(step)
        self.session.commit()

    def _create_agent_task(self, step_id: str, prompt: str) -> AgentTask:
        task = AgentTask(step_id=step_id, prompt=prompt, status="running")
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def _complete_agent_task(
        self,
        task: AgentTask,
        response: str,
        error_logs: str | None = None,
    ) -> None:
        task.response = response
        task.error_logs = error_logs
        task.status = "completed" if error_logs is None else "failed"
        self.session.add(task)
        self.session.commit()

    def _read_spec(self, spec_path: str) -> str:
        try:
            with open(spec_path) as f:
                return f.read()
        except OSError:
            return ""

    def _run_verification(self, commands: list[str]) -> dict[str, Any]:
        results: dict[str, Any] = {}
        with LocalSandbox(workdir=self.sandbox_workdir) as sandbox:
            for cmd in commands:
                results[cmd] = sandbox.execute(cmd)
        return results

    def _run_development_loop(
        self,
        workflow: Workflow,
        step_title: str,
        agent_id: str,
        requirements: str,
        plan: str,
        verification_commands: list[str],
    ) -> str:
        step = self._create_step(workflow.id, step_title, agent_id)
        self._start_step(step)

        code = ""
        feedback = ""
        success = False

        for iteration in range(self.max_retries):
            prompt = (
                f"Iteration {iteration + 1}: "
                f"requirements={requirements}, feedback={feedback}"
            )
            task = self._create_agent_task(step.id, prompt)
            try:
                dev_result = self.developer.run(
                    {
                        "requirements": requirements,
                        "plan": plan,
                        "file_path": workflow.spec_path,
                        "current_content": code,
                        "feedback": feedback,
                    }
                )
                code = dev_result["code"]
                self._complete_agent_task(task, code)

                verification_results = self._run_verification(verification_commands)
                failed_commands = [
                    cmd
                    for cmd, res in verification_results.items()
                    if res.get("exit_code", -1) != 0
                ]

                if not failed_commands:
                    success = True
                    break

                feedback = "\n".join(
                    f"{cmd}:\n{verification_results[cmd].get('stderr', '')}"
                    for cmd in failed_commands
                )
            except Exception as exc:
                self._complete_agent_task(task, "", str(exc))
                feedback = str(exc)

        self._complete_step(step, success=success)

        if not success:
            raise RuntimeError(
                f"Step '{step_title}' failed after {self.max_retries} retries."
            )

        return code

    def _run_planner_step(
        self, workflow: Workflow, step_title: str, requirements: str
    ) -> str:
        step = self._create_step(workflow.id, step_title, "planner")
        self._start_step(step)
        task = self._create_agent_task(step.id, requirements)
        try:
            result = self.planner.run(
                {"requirements": requirements, "code_context": ""}
            )
            plan = str(result["plan"])
            self._complete_agent_task(task, plan)
            self._complete_step(step, success=True)
            return plan
        except Exception as exc:
            self._complete_agent_task(task, "", str(exc))
            self._complete_step(step, success=False)
            raise

    def _run_review_step(
        self, workflow: Workflow, code: str, requirements: str, parallel: bool = False
    ) -> None:
        step = self._create_step(workflow.id, "Review", "reviewer")
        self._start_step(step)

        if parallel:
            with ThreadPoolExecutor(max_workers=2) as executor:
                review_future = executor.submit(
                    self.reviewer.run,
                    {
                        "code": code,
                        "file_path": workflow.spec_path,
                        "requirements": requirements,
                    },
                )
                validator_future = executor.submit(
                    self.validator.run,
                    {
                        "code": code,
                        "requirements": requirements,
                        "file_path": workflow.spec_path,
                    },
                )
                review_result = review_future.result()
                validation_result = validator_future.result()

            review_passed = review_result.get("approved", False) and validation_result.get(
                "valid", False
            )
            response_str = (
                f"approved={review_result.get('approved')}, "
                f"valid={validation_result.get('valid')}"
            )
            error_logs: str | None = None
            if not review_passed:
                error_logs = (
                    f"review: {review_result.get('comments')}\n"
                    f"validation: {validation_result.get('comments')}"
                )
        else:
            review_result = self.reviewer.run(
                {
                    "code": code,
                    "file_path": workflow.spec_path,
                    "requirements": requirements,
                }
            )
            review_passed = review_result.get("approved", False)
            response_str = str(review_result.get("approved"))
            error_logs = (
                None if review_passed else str(review_result.get("comments"))
            )

        task = self._create_agent_task(step.id, f"review: {workflow.spec_path}")
        self._complete_agent_task(task, response_str, error_logs)
        self._complete_step(step, success=review_passed)

        if not review_passed:
            raise RuntimeError("Review step failed.")

    def _run_full_sdd(self, workflow: Workflow) -> None:
        requirements = self._read_spec(workflow.spec_path)

        plan = self._run_planner_step(workflow, "Planning", requirements)

        code = self._run_development_loop(
            workflow=workflow,
            step_title="Development",
            agent_id="developer",
            requirements=requirements,
            plan=plan,
            verification_commands=["pytest", "ruff check ."],
        )

        self._run_review_step(workflow, code, requirements, parallel=True)

    def _run_fix_bug(self, workflow: Workflow) -> None:
        requirements = self._read_spec(workflow.spec_path)

        code = self._run_development_loop(
            workflow=workflow,
            step_title="Bug Fix",
            agent_id="developer",
            requirements=requirements,
            plan="",
            verification_commands=["pytest"],
        )

        self._run_review_step(workflow, code, requirements, parallel=False)

    def _run_refactor(self, workflow: Workflow) -> None:
        requirements = self._read_spec(workflow.spec_path)

        plan = self._run_planner_step(workflow, "Refactor Planning", requirements)

        code = self._run_development_loop(
            workflow=workflow,
            step_title="Refactoring",
            agent_id="developer",
            requirements=requirements,
            plan=plan,
            verification_commands=["pytest", "ruff check ."],
        )

        self._run_review_step(workflow, code, requirements, parallel=False)
