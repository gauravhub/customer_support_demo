"""Middleware for injecting knowledgeBaseId into tool calls and updating state.

This module contains middleware for:
- Injecting knowledgeBaseId into query_products_kb tool calls
- Updating state after tool calls based on tool results
"""

import json
import logging
from typing import Any, Awaitable, Callable, Dict

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from agent.state import CustomerSupportState


logger = logging.getLogger(__name__)


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


class StateUpdateMiddleware(AgentMiddleware[CustomerSupportState]):
    """Middleware to update state after tool calls.
    
    This middleware intercepts tool results and updates state fields based on
    the tool that was called and its result:
    - get_issue: Updates issue_no, summary, description, category, assignee, reporter, attachments
    - find_customer: Updates customer_email, customer_name
    - updateIsInConversationModeFlag: Updates isInConversationMode to True
    - updateInitiateIssueAnalysisFlag: Updates initiateIssueAnalysis to True
    """
    state_schema = CustomerSupportState  # Extend agent state to include CustomerSupportState fields
    
    async def awrap_tool_call(
        self,
        request: Any,  # ToolCallRequest
        handler: Callable[[Any], Awaitable[ToolMessage | Command | Any]]
    ) -> ToolMessage | Command | Any:
        """Wrap tool calls to update state after execution.
        
        Args:
            request: ToolCallRequest containing tool call information
            handler: Next handler in the middleware chain
            
        Returns:
            Command with state updates, or original result if no updates needed
        """
        logger.info(f"StateUpdateMiddleware: awrap_tool_call invoked (request type: {type(request).__name__})")
        
        # Get tool name from request
        tool_name = None
        if hasattr(request, 'tool_call'):
            tool_call = request.tool_call
            logger.debug(f"StateUpdateMiddleware: request.tool_call type: {type(tool_call).__name__}, value: {tool_call}")
            if isinstance(tool_call, dict):
                tool_name = tool_call.get('name')
        else:
            logger.debug(f"StateUpdateMiddleware: request attributes: {dir(request)}")
        
        if not tool_name:
            # No tool name, just pass through
            logger.debug("StateUpdateMiddleware: No tool name found in request, skipping state update")
            return await handler(request)
        
        logger.info(f"StateUpdateMiddleware: Intercepted tool call: {tool_name}")
        
        # Execute the tool
        result = await handler(request)
        
        # Extract ToolMessage from result
        tool_message = None
        if isinstance(result, ToolMessage):
            tool_message = result
        elif isinstance(result, Command) and result.update and result.update.get("messages"):
            # Command already contains messages, extract the ToolMessage
            messages = result.update.get("messages", [])
            tool_message = messages[0] if messages and isinstance(messages[0], ToolMessage) else None
        
        if not tool_message:
            # No ToolMessage found, return original result
            logger.info(
                f"StateUpdateMiddleware: No ToolMessage found in result for {tool_name}, "
                f"skipping state update (result type: {type(result).__name__})"
            )
            return result
        
        # Parse tool result from ToolMessage content
        content = tool_message.content
        logger.info(f"StateUpdateMiddleware: ToolMessage content type: {type(content).__name__}, content: {content}")
        tool_result = None
        
        # Handle LangChain's structured content format (list of content blocks)
        if isinstance(content, list) and len(content) > 0:
            # Content is a list of content blocks (e.g., [{'type': 'text', 'text': '...', 'id': '...'}])
            # Extract text from the first block
            first_block = content[0]
            if isinstance(first_block, dict) and first_block.get("type") == "text":
                # The actual JSON data is in the 'text' field as a string
                text_content = first_block.get("text", "")
                if text_content:
                    try:
                        tool_result = json.loads(text_content)
                    except (json.JSONDecodeError, TypeError):
                        # If not JSON, try to extract JSON from the string
                        if "{" in text_content or "[" in text_content:
                            try:
                                start_idx = text_content.find("{")
                                end_idx = text_content.rfind("}") + 1
                                if start_idx >= 0 and end_idx > start_idx:
                                    json_str = text_content[start_idx:end_idx]
                                    tool_result = json.loads(json_str)
                                else:
                                    tool_result = text_content
                            except (json.JSONDecodeError, ValueError):
                                tool_result = text_content
                        else:
                            tool_result = text_content
            else:
                # If first item is a dict but not a text block, use it as-is
                tool_result = content[0] if isinstance(content[0], dict) else content
        elif isinstance(content, str):
            # Content is a plain string, try to parse as JSON
            try:
                tool_result = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                # Try to extract JSON from the string if it contains JSON
                if "{" in content or "[" in content:
                    try:
                        start_idx = content.find("{")
                        end_idx = content.rfind("}") + 1
                        if start_idx >= 0 and end_idx > start_idx:
                            json_str = content[start_idx:end_idx]
                            tool_result = json.loads(json_str)
                        else:
                            tool_result = content
                    except (json.JSONDecodeError, ValueError):
                        tool_result = content
                else:
                    tool_result = content
        elif isinstance(content, dict):
            tool_result = content
        else:
            # Unknown content type, skip state update
            logger.debug(
                f"StateUpdateMiddleware: Unknown content type for tool {tool_name}: "
                f"{type(content)}, skipping state update"
            )
            return result
        
        # Skip if tool_result is empty or error
        if not tool_result:
            logger.info(
                f"StateUpdateMiddleware: Tool {tool_name} returned empty result, "
                "skipping state update"
            )
            return result
        
        # Skip if tool_result is a dict with an error
        if isinstance(tool_result, dict) and tool_result.get("error"):
            logger.info(
                f"StateUpdateMiddleware: Tool {tool_name} returned error in result, "
                "skipping state update"
            )
            return result
        
        # Build state updates based on tool name
        logger.info(f"StateUpdateMiddleware: Parsed tool_result type: {type(tool_result).__name__}, value: {tool_result}")
        state_updates: Dict[str, Any] = {}
        
        if tool_name == "get_issue":
            # Update issue-related fields from get_issue result
            logger.info(f"StateUpdateMiddleware: Checking if tool_result is dict for {tool_name}: {isinstance(tool_result, dict)}")
            if isinstance(tool_result, dict):
                logger.info(f"StateUpdateMiddleware: tool_result keys for {tool_name}: {list(tool_result.keys())}")
                if "key" in tool_result:
                    state_updates["issue_no"] = tool_result["key"]
                if "summary" in tool_result:
                    state_updates["summary"] = tool_result["summary"]
                if "description" in tool_result:
                    state_updates["description"] = tool_result["description"]
                if "assignee" in tool_result:
                    state_updates["assignee"] = tool_result["assignee"]
                if "reporter" in tool_result:
                    state_updates["reporter"] = tool_result["reporter"]
                # Extract custom fields: Category and Response
                # Category is a custom JIRA field (Transaction, Delivery, Refunds, Other)
                # This is different from issue_type (Problem, Bug, Task, etc.)
                if "category" in tool_result:
                    state_updates["category"] = tool_result["category"]
                if "response" in tool_result:
                    state_updates["response"] = tool_result["response"]
                # Extract attachments (list of download URLs)
                if "attachments" in tool_result:
                    attachments = tool_result["attachments"]
                    logger.info(
                        f"StateUpdateMiddleware: Found attachments in {tool_name} result: "
                        f"type={type(attachments).__name__}, value={attachments}"
                    )
                    if isinstance(attachments, list):
                        # Note: attachments uses operator.add in state, so passing a list will
                        # add each item to the existing list. To replace, we pass the full list
                        # and LangGraph will add each item. If list is empty initially, this works.
                        # If we need to replace existing items, we'd need a different approach.
                        state_updates["attachments"] = attachments
                        logger.info(
                            f"StateUpdateMiddleware: Extracted {len(attachments)} attachments "
                            f"from {tool_name}: {attachments}"
                        )
                    else:
                        logger.warning(
                            f"StateUpdateMiddleware: attachments in {tool_name} result is not a list: "
                            f"{type(attachments).__name__}"
                        )
                else:
                    logger.debug(
                        f"StateUpdateMiddleware: No 'attachments' key found in {tool_name} result. "
                        f"Available keys: {list(tool_result.keys()) if isinstance(tool_result, dict) else 'N/A'}"
                    )
                logger.info(
                    f"StateUpdateMiddleware: Built state updates for {tool_name}: "
                    f"{list(state_updates.keys())} = {state_updates}"
                )
                # Explicitly log if attachments are in state_updates
                if "attachments" in state_updates:
                    logger.info(
                        f"StateUpdateMiddleware: ✓ Attachments included in state_updates for {tool_name}: "
                        f"{state_updates['attachments']}"
                    )
                elif "attachments" in tool_result:
                    logger.warning(
                        f"StateUpdateMiddleware: ✗ Attachments found in tool_result but NOT in state_updates for {tool_name}. "
                        f"tool_result attachments: {tool_result.get('attachments')}"
                    )
            else:
                logger.info(
                    f"StateUpdateMiddleware: Tool {tool_name} result is not a dict "
                    f"(type: {type(tool_result).__name__}), skipping state update"
                )
        
        elif tool_name == "find_customer":
            # Update customer-related fields from find_customer result
            logger.info(f"StateUpdateMiddleware: Checking if tool_result is dict for {tool_name}: {isinstance(tool_result, dict)}")
            if isinstance(tool_result, dict):
                logger.info(f"StateUpdateMiddleware: tool_result keys for {tool_name}: {list(tool_result.keys())}")
                if "email" in tool_result:
                    state_updates["customer_email"] = tool_result["email"]
                if "name" in tool_result:
                    # Capitalize the name properly (e.g., "morgan taylor" -> "Morgan Taylor")
                    name = tool_result["name"]
                    state_updates["customer_name"] = name.title() if name else name
                logger.info(
                    f"StateUpdateMiddleware: Built state updates for {tool_name}: "
                    f"{list(state_updates.keys())} = {state_updates}"
                )
            else:
                logger.info(
                    f"StateUpdateMiddleware: Tool {tool_name} result is not a dict "
                    f"(type: {type(tool_result).__name__}), skipping state update"
                )
        
        elif tool_name == "updateIsInConversationModeFlag":
            # Update conversation mode flag
            logger.info(f"StateUpdateMiddleware: Handling {tool_name} tool call")
            state_updates["isInConversationMode"] = True
            logger.info(
                f"StateUpdateMiddleware: Built state updates for {tool_name}: "
                f"{list(state_updates.keys())} = {state_updates}"
            )
        elif tool_name == "updateInitiateIssueAnalysisFlag":
            # Update issue analysis flag to True
            logger.info(f"StateUpdateMiddleware: Handling {tool_name} tool call")
            state_updates["initiateIssueAnalysis"] = True
            logger.info(
                f"StateUpdateMiddleware: Built state updates for {tool_name}: "
                f"{list(state_updates.keys())} = {state_updates}"
            )
        elif tool_name == "resetInitiateIssueAnalysisFlag":
            # Reset issue analysis flag to False
            logger.info(f"StateUpdateMiddleware: Handling {tool_name} tool call")
            state_updates["initiateIssueAnalysis"] = False
            logger.info(
                f"StateUpdateMiddleware: Built state updates for {tool_name}: "
                f"{list(state_updates.keys())} = {state_updates}"
            )
        elif tool_name == "update_issue_field" or (isinstance(tool_name, str) and "update_issue_field" in tool_name):
            # Handle update_issue_field - extract value from tool call arguments when field_name="response"
            logger.info(f"StateUpdateMiddleware: Handling {tool_name} tool call")
            
            # Extract tool call arguments from request
            tool_args = {}
            if hasattr(request, 'tool_call'):
                tool_call = request.tool_call
                if isinstance(tool_call, dict):
                    tool_args = tool_call.get('args', {})
                elif hasattr(tool_call, 'args'):
                    tool_args = tool_call.args if isinstance(tool_call.args, dict) else {}
            
            # Check if this is updating the response field
            field_name = tool_args.get('field_name', '')
            if field_name == "response":
                value = tool_args.get('value', '')
                if value:
                    state_updates["response"] = value
                    logger.info(
                        f"StateUpdateMiddleware: Built state updates for {tool_name}: "
                        f"response = {value[:100] if len(str(value)) > 100 else value}..."
                    )
                else:
                    logger.warning(f"StateUpdateMiddleware: {tool_name} called with field_name='response' but no value provided")
            else:
                logger.debug(f"StateUpdateMiddleware: {tool_name} called with field_name='{field_name}', not updating state")
        else:
            logger.info(
                f"StateUpdateMiddleware: Tool {tool_name} is not configured for state updates "
                "(only 'get_issue', 'find_customer', 'updateIsInConversationModeFlag', 'updateInitiateIssueAnalysisFlag', 'resetInitiateIssueAnalysisFlag', and 'update_issue_field' are supported), skipping"
            )
        
        # If we have state updates, return Command with updates
        if state_updates:
            logger.info(
                f"StateUpdateMiddleware: Updating state after {tool_name} tool call with fields: "
                f"{list(state_updates.keys())}"
            )
            # Explicitly log attachments in state_updates before creating Command
            if "attachments" in state_updates:
                logger.info(
                    f"StateUpdateMiddleware: ✓ Attachments will be included in Command update: "
                    f"{state_updates['attachments']} (type: {type(state_updates['attachments']).__name__})"
                )
            
            # Preserve existing Command updates if result is already a Command
            if isinstance(result, Command):
                existing_updates = result.update or {}
                # Merge state updates with existing updates
                merged_updates = {
                    **existing_updates,
                    **state_updates,
                }
                # Preserve messages from existing Command
                if "messages" not in merged_updates and existing_updates.get("messages"):
                    merged_updates["messages"] = existing_updates["messages"]
                elif "messages" not in merged_updates:
                    merged_updates["messages"] = [tool_message]
                
                logger.debug(
                    f"StateUpdateMiddleware: Merged state updates with existing Command updates "
                    f"for {tool_name}"
                )
                return Command(
                    update=merged_updates,
                    goto=result.goto if hasattr(result, 'goto') else None
                )
            else:
                # Create new Command with state updates
                logger.info(
                    f"StateUpdateMiddleware: Creating new Command with state updates for {tool_name}: "
                    f"{state_updates}"
                )
                return Command(
                    update={
                        **state_updates,
                        "messages": [tool_message],
                    }
                )
        
        # No state updates needed, return original result
        logger.info(
            f"StateUpdateMiddleware: No state updates needed for {tool_name}, "
            "returning original result"
        )
        return result
