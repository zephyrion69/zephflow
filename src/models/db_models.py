import uuid
from datetime import datetime
from typing import ClassVar

from sqlmodel import Field, Relationship, SQLModel


class RepositoryConfig(SQLModel, table=True):
    __tablename__: ClassVar[str] = "repository_config"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    url: str
    local_path: str
    branch: str

    workflows: list["Workflow"] = Relationship(back_populates="repository")


class Workflow(SQLModel, table=True):
    __tablename__: ClassVar[str] = "workflow"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    repo_id: str | None = Field(default=None, foreign_key="repository_config.id")
    spec_path: str
    status: str
    type: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    repository: RepositoryConfig | None = Relationship(back_populates="workflows")
    steps: list["WorkflowStep"] = Relationship(back_populates="workflow")


class WorkflowStep(SQLModel, table=True):
    __tablename__: ClassVar[str] = "workflow_step"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    workflow_id: str | None = Field(default=None, foreign_key="workflow.id")
    title: str
    status: str
    agent_id: str | None = Field(default=None)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)

    workflow: Workflow | None = Relationship(back_populates="steps")
    agent_tasks: list["AgentTask"] = Relationship(back_populates="step")


class AgentTask(SQLModel, table=True):
    __tablename__: ClassVar[str] = "agent_task"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    step_id: str | None = Field(default=None, foreign_key="workflow_step.id")
    prompt: str
    response: str | None = Field(default=None)
    error_logs: str | None = Field(default=None)
    status: str

    step: WorkflowStep | None = Relationship(back_populates="agent_tasks")
    sandbox_sessions: list["SandboxSession"] = Relationship(back_populates="agent_task")


class SandboxSession(SQLModel, table=True):
    __tablename__: ClassVar[str] = "sandbox_session"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    task_id: str | None = Field(default=None, foreign_key="agent_task.id")
    container_id: str | None = Field(default=None)
    status: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    agent_task: AgentTask | None = Relationship(back_populates="sandbox_sessions")
