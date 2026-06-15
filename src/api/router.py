import hashlib
import hmac
import logging
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from src.core.config import settings
from src.core.database import get_session
from src.models.db_models import RepositoryConfig, Workflow, WorkflowStep
from src.workflows.engine import WorkflowEngine, WorkflowStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

SessionDep = Annotated[Session, Depends(get_session)]


class WorkflowTriggerRequest(BaseModel):
    repository_id: str | None = None
    workflow_type: str
    spec_file_path: str


class WorkflowTriggerResponse(BaseModel):
    id: str
    status: str
    type: str
    spec_path: str
    repo_id: str | None


class WorkflowStepResponse(BaseModel):
    id: str
    title: str
    status: str
    agent_id: str | None


class WorkflowStatusResponse(BaseModel):
    id: str
    status: str
    type: str
    spec_path: str
    steps: list[WorkflowStepResponse]


class RepositoryCreateRequest(BaseModel):
    url: str
    branch: str
    local_path: str


class RepositoryResponse(BaseModel):
    id: str
    url: str
    local_path: str
    branch: str


class WebhookResponse(BaseModel):
    workflow_id: str
    message: str


def _verify_github_signature(payload: bytes, signature: str | None) -> bool:
    secret = settings.GITHUB_WEBHOOK_SECRET
    if not secret:
        return True
    if not signature:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _run_workflow_background(workflow_id: str, session: Session) -> None:
    try:
        engine = WorkflowEngine(session=session)
        engine.run(workflow_id)
    except Exception:
        logger.exception("Background workflow %s failed", workflow_id)


@router.post("/webhooks/github", response_model=WebhookResponse, status_code=202)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    x_hub_signature_256: str | None = Header(default=None),
) -> WebhookResponse:
    payload = await request.body()

    if not _verify_github_signature(payload, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    body: dict[str, Any] = await request.json()
    event = request.headers.get("X-GitHub-Event", "")

    if event not in ("pull_request", "push"):
        return WebhookResponse(workflow_id="", message=f"Event '{event}' ignored")

    repo_url: str = (
        body.get("repository", {}).get("clone_url", "")
        or body.get("repository", {}).get("html_url", "")
    )
    spec_path = body.get("spec_path", "spec.md")

    repo_config = session.exec(
        select(RepositoryConfig).where(RepositoryConfig.url == repo_url)
    ).first()

    workflow = Workflow(
        repo_id=repo_config.id if repo_config else None,
        spec_path=spec_path,
        status=WorkflowStatus.PENDING,
        type="fix_bug" if event == "push" else "full_sdd",
    )
    session.add(workflow)
    session.commit()
    session.refresh(workflow)

    background_tasks.add_task(_run_workflow_background, workflow.id, session)

    return WebhookResponse(
        workflow_id=workflow.id,
        message="Workflow initiated",
    )


@router.post(
    "/workflows/trigger",
    response_model=WorkflowTriggerResponse,
    status_code=201,
)
def trigger_workflow(
    body: WorkflowTriggerRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> WorkflowTriggerResponse:
    if body.workflow_type not in ("full_sdd", "fix_bug", "refactor"):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid workflow_type '{body.workflow_type}'",
        )

    if body.repository_id:
        repo = session.get(RepositoryConfig, body.repository_id)
        if repo is None:
            raise HTTPException(
                status_code=404,
                detail=f"Repository '{body.repository_id}' not found",
            )

    workflow = Workflow(
        repo_id=body.repository_id,
        spec_path=body.spec_file_path,
        status=WorkflowStatus.PENDING,
        type=body.workflow_type,
    )
    session.add(workflow)
    session.commit()
    session.refresh(workflow)

    background_tasks.add_task(_run_workflow_background, workflow.id, session)

    return WorkflowTriggerResponse(
        id=workflow.id,
        status=workflow.status,
        type=workflow.type,
        spec_path=workflow.spec_path,
        repo_id=workflow.repo_id,
    )


@router.get("/workflows/{workflow_id}", response_model=WorkflowStatusResponse)
def get_workflow_status(
    workflow_id: str, session: SessionDep
) -> WorkflowStatusResponse:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(
            status_code=404, detail=f"Workflow '{workflow_id}' not found"
        )

    steps = session.exec(
        select(WorkflowStep).where(WorkflowStep.workflow_id == workflow_id)
    ).all()

    return WorkflowStatusResponse(
        id=workflow.id,
        status=workflow.status,
        type=workflow.type,
        spec_path=workflow.spec_path,
        steps=[
            WorkflowStepResponse(
                id=s.id,
                title=s.title,
                status=s.status,
                agent_id=s.agent_id,
            )
            for s in steps
        ],
    )


@router.post("/repositories", response_model=RepositoryResponse, status_code=201)
def create_repository(
    body: RepositoryCreateRequest, session: SessionDep
) -> RepositoryResponse:
    repo = RepositoryConfig(
        url=body.url,
        local_path=body.local_path,
        branch=body.branch,
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)

    return RepositoryResponse(
        id=repo.id,
        url=repo.url,
        local_path=repo.local_path,
        branch=repo.branch,
    )


@router.get("/repositories", response_model=list[RepositoryResponse])
def list_repositories(session: SessionDep) -> list[RepositoryResponse]:
    repos = session.exec(select(RepositoryConfig)).all()
    return [
        RepositoryResponse(
            id=r.id,
            url=r.url,
            local_path=r.local_path,
            branch=r.branch,
        )
        for r in repos
    ]
