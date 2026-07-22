from __future__ import annotations


class AgentRunWorkflowError(RuntimeError):
    pass


class AgentRunAlreadyActiveError(AgentRunWorkflowError):
    pass


class AgentRunClaimLostError(AgentRunWorkflowError):
    pass


class AgentRunNotFoundError(AgentRunWorkflowError):
    pass
