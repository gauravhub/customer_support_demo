"""Custom tools for the customer support agent.

This module contains custom tools that update state fields directly.
"""

from langchain_core.tools import tool


@tool
def updateIsInConversationModeFlag() -> str:
    """Update the isInConversationMode flag in the state.
    
    This tool updates the isInConversationMode state field to True,
    indicating that conversation mode is now active.
    
    This tool should be called when transitioning to conversation mode
    after successfully validating customer information.
    
    Returns:
        Success message confirming the state update
    """
    # This tool returns a success message
    # The actual state update is handled by StateUpdateMiddleware
    return "Conversation mode flag has been updated successfully."


@tool
def updateInitiateIssueAnalysisFlag() -> str:
    """Update the initiateIssueAnalysis flag in the state.
    
    This tool updates the initiateIssueAnalysis state field to True,
    indicating that issue analysis phase should be initiated.
    
    This tool should be called after successfully validating customer information
    and before proceeding with triage response.
    
    Returns:
        Success message confirming the state update
    """
    # This tool returns a success message
    # The actual state update is handled by StateUpdateMiddleware
    return "Issue analysis flag has been updated successfully."


@tool
def resetInitiateIssueAnalysisFlag() -> str:
    """Reset the initiateIssueAnalysis flag in the state.
    
    This tool updates the initiateIssueAnalysis state field to False,
    indicating that issue analysis phase has been completed.
    
    This tool should be called after response generation is complete
    to reset the flag for future workflows.
    
    Returns:
        Success message confirming the state update
    """
    # This tool returns a success message
    # The actual state update is handled by StateUpdateMiddleware
    return "Issue analysis flag has been reset successfully."
