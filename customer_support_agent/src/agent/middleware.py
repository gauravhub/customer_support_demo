"""Middleware for injecting knowledgeBaseId into tool calls.

This middleware intercepts tool calls and automatically injects the configured
Product Knowledge Base ID into the query_products_kb tool.
"""

from typing import Any, Callable, Awaitable
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from agent.configuration import Configuration


class KnowledgeBaseIDMiddleware(AgentMiddleware):
    """Middleware to automatically inject knowledgeBaseId into tool calls.
    
    This middleware intercepts tool invocations and injects the configured
    Product Knowledge Base ID into the query_products_kb tool before execution.
    This ensures the tool always has the correct KB ID without requiring
    the agent to provide it.
    """
    
    def __init__(self, kb_id: str, tool_name: str = "query_products_kb"):
        """Initialize the middleware.
        
        Args:
            kb_id: Product Knowledge Base ID to inject
            tool_name: Name of the tool to inject KB ID into (default: "query_products_kb")
        """
        self.kb_id = kb_id
        self.tool_name = tool_name
    
    async def awrap_tool_call(
        self,
        request: Any,  # ToolCallRequest (forward reference, can't import directly)
        handler: Callable[[Any], Awaitable[ToolMessage | Any]]
    ) -> ToolMessage | Any:
        """Wrap tool calls to inject knowledgeBaseId (async version).
        
        This method is called before each tool invocation. If the tool is
        the query_products_kb tool, it injects the knowledgeBaseId.
        
        Args:
            request: ToolCallRequest containing tool call information
            handler: Next handler in the middleware chain
            
        Returns:
            ToolMessage or Command from the tool execution
        """
        # Access the tool call from the request
        # ToolCallRequest has a 'tool_call' attribute which is a dict with 'name', 'args', and 'id'
        if hasattr(request, 'tool_call'):
            tool_call = request.tool_call
            
            # tool_call is a dict with 'name' and 'args' keys
            if isinstance(tool_call, dict):
                tool_name = tool_call.get('name')
                tool_input = tool_call.get('args')
                
                # Only inject for the specific tool
                if tool_name == self.tool_name and tool_input is not None:
                    # Handle different input types
                    if isinstance(tool_input, dict):
                        # Always inject/override knowledgeBaseId
                        tool_input['knowledgeBaseId'] = self.kb_id
                    elif hasattr(tool_input, 'model_dump'):
                        # Pydantic model - convert to dict, inject, and update
                        tool_input_dict = tool_input.model_dump()
                        tool_input_dict['knowledgeBaseId'] = self.kb_id
                        # Update the tool_call args with the modified dict
                        tool_call['args'] = tool_input_dict
                    elif hasattr(tool_input, '__dict__'):
                        # Object with __dict__ - inject as attribute
                        setattr(tool_input, 'knowledgeBaseId', self.kb_id)
                        # Also update the dict reference
                        if isinstance(tool_input.__dict__, dict):
                            tool_input.__dict__['knowledgeBaseId'] = self.kb_id
        
        # Call the next handler in the chain
        return await handler(request)
