from __future__ import annotations

from app.services.agent_harness.workflow.scheduler import WorkflowStepScheduler


class WorkflowStepWorkerLoop(WorkflowStepScheduler):
    """Worker loop for durable agent workflow steps."""

