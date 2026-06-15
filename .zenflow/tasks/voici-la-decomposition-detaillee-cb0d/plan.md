# Full SDD workflow

## Configuration
- **Artifacts Path**: {@artifacts_path} → `.zenflow/tasks/{task_id}`

---

## Agent Instructions

---

## Workflow Steps

### [x] Step: Requirements
<!-- chat-id: e60d8989-9fa0-49f2-9a13-2bb134c20f02 -->

Create a Product Requirements Document (PRD) based on the feature description.

1. Review existing codebase to understand current architecture and patterns
2. Analyze the feature definition and identify unclear aspects
3. Ask the user for clarifications on aspects that significantly impact scope or user experience
4. Make reasonable decisions for minor details based on context and conventions
5. If user can't clarify, make a decision, state the assumption, and continue

Focus on **what** the feature should do and **why**, not **how** it should be built. Do not include technical implementation details, technology choices, or code-level decisions — those belong in the Technical Specification.

Save the PRD to `{@artifacts_path}/requirements.md`.

### [x] Step: Technical Specification
<!-- chat-id: 5b22849a-c735-4b13-a46a-c237939213ff -->

Create a technical specification based on the PRD in `{@artifacts_path}/requirements.md`.

1. Review existing codebase architecture and identify reusable components
2. Define the implementation approach

Do not include implementation steps, phases, or task breakdowns — those belong in the Planning step.

Save to `{@artifacts_path}/spec.md` with:
- Technical context (language, dependencies)
- Implementation approach referencing existing code patterns
- Source code structure changes
- Data model / API / interface changes
- Verification approach using project lint/test commands

### [x] Step: Planning
<!-- chat-id: ef84c99f-452a-4741-909c-98b4c818f3b0 -->

Create a detailed implementation plan based on `.\.zenflow\tasks\voici-la-decomposition-detaillee-cb0d\spec.md`.

1. Break down the work into concrete tasks
2. Each task should reference relevant contracts and include verification steps
3. Replace the Implementation step below with the planned tasks

Rule of thumb for step size: each step should represent a coherent unit of work (e.g., implement a component, add an API endpoint). Avoid steps that are too granular (single function) or too broad (entire feature).

Important: unit tests must be part of each implementation task, not separate tasks. Each task should implement the code and its tests together, if relevant.

If the feature is trivial and doesn't warrant full specification, update this workflow to remove unnecessary steps and explain the reasoning to the user.

Save to `.\.zenflow\tasks\voici-la-decomposition-detaillee-cb0d\plan.md`.

### [x] Step: Project Setup and Core Configuration
<!-- chat-id: 06cc807d-0ac1-4ee4-b0bc-940e55b8d782 -->
Configure dependencies, base settings, data structures, and the persistent SQLite database layer.
- **Contract/Files**:
  - `.\requirements.txt`: List and pin dependencies like `fastapi`, `pydantic`, `langchain-core`, `sqlmodel`, `gitpython`, `docker`, and `apscheduler`.
  - `.\pyproject.toml`: Settings for pytest, ruff, and mypy.
  - `.\src\core\config.py`: Application configurations and LLM API keys.
  - `.\src\core\database.py`: DB engine and session creation.
  - `.\src\models\db_models.py`: SQLModel schemas for repositories, workflows, steps, tasks, and sandbox sessions.
- **Verification**:
  - Implement unit tests in `.\tests\test_core.py` to check config loading and DB model definitions.
  - Run `pytest .\tests\test_core.py` and run quality/linter checks.

### [x] Step: Sandbox Execution Environments
<!-- chat-id: 7bcaa2c3-ca1a-4de7-a515-7ba715e908b1 -->
Build the isolated runtime sandbox layers to support execution of verification scripts and tools.
- **Contract/Files**:
  - `.\src\sandbox\base.py`: Define `BaseSandbox` abstract interface.
  - `.\src\sandbox\local_sandbox.py`: Implement subprocess-based sandbox for local testing.
  - `.\src\sandbox\docker_sandbox.py`: Implement docker-based sandbox using python docker SDK.
- **Verification**:
  - Implement unit tests in `.\tests\test_sandbox.py` to verify command execution, error logging, and timeout Handling.
  - Run `pytest .\tests\test_sandbox.py`.

### [x] Step: Multi-Repository Git Manager
<!-- chat-id: 8f3f7c00-b11d-43be-afe4-8c56f5365913 -->
Implement a manager capable of orchestrating multi-repo checkouts, branching, and status checks.
- **Contract/Files**:
  - `.\src\repository\manager.py`: Service managing multiple local Git directories using GitPython.
- **Verification**:
  - Implement unit tests in `.\tests\test_repository.py` using mocked Git repositories.
  - Run `pytest .\tests\test_repository.py`.

### [x] Step: Base and Specialized Agents
<!-- chat-id: 69e968c4-5698-4eb8-bb35-0b5fe0c9e429 -->
Create the agent base class and concrete specialised agents with distinct system prompts and tools.
- **Contract/Files**:
  - `.\src\agents\base.py`: Abstract agent layer.
  - `.\src\agents\planner.py`: Planner agent.
  - `.\src\agents\developer.py`: Developer agent.
  - `.\src\agents\reviewer.py`: Reviewer agent.
  - `.\src\agents\spec_validator.py`: Spec validator agent.
- **Verification**:
  - Implement unit tests in `.\tests\test_agents.py` with mock LLM responses verifying correct prompt structures.
  - Run `pytest .\tests\test_agents.py`.

### [x] Step: Workflow Orchestration Engine
<!-- chat-id: 7eeefa37-68e3-442d-a564-9ab6fe5fecf9 -->
Build the orchestrator that manages sequential/parallel steps, feedback loops, and multi-agent coordination.
- **Contract/Files**:
  - `.\src\workflows\engine.py`: Core workflow execution engine supporting `full_sdd`, `fix_bug`, and `refactor` workflows.
- **Verification**:
  - Implement unit tests in `.\tests\test_workflow_engine.py` using mock database states and agents.
  - Run `pytest .\tests\test_workflow_engine.py`.

### [x] Step: FastAPI Webhook API, Scheduler, and Main Entry
<!-- chat-id: a8580b7e-df1b-43be-96d6-9ebcd4d3c7bc -->
Expose Webhook and Trigger APIs, configure background Cron scheduling, and compile the application entry point.
- **Contract/Files**:
  - `.\src\api\router.py`: API endpoints for Github Webhooks, manual triggers, and workflow status.
  - `.\src\scheduler\cron.py`: Cron scheduler wrapper.
  - `.\src\main.py`: ASGI entry point.
- **Verification**:
  - Implement integration tests in `.\tests\test_api.py` using FastAPI's `TestClient`.
  - Run `pytest .\tests\test_api.py`, run `ruff check .` and `mypy .\src`.
