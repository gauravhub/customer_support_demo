"""Issue analysis workflow nodes.

This module contains nodes for analyzing customer support issues:
1. Analyze Summary - Extract order_no from summary/description
2. Analyze Attachments - Download and analyze attachments to extract transaction_id
3. Determine Category - Categorize issue and update in Jira
4. Assign Support Contact - Assign issue to configured assignee
5. Generate Response - (To be implemented later)
"""

import asyncio
import json
import logging
from typing import Any, Dict
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from agent.configuration import Configuration
from agent.state import CustomerSupportState
from agent.middleware import StateUpdateMiddleware
from agent.prompts import (
    get_categorization_prompt,
    get_extract_order_number_prompt,
    get_analyze_attachments_prompt,
    get_response_generation_system_prompt,
)
from agent.tools import resetInitiateIssueAnalysisFlag, updateIsInConversationModeFlag
from agent.utils import (
    add_image_content,
    download_attachment,
    extract_json_from_response,
    extract_text_content,
)
from services.bedrock import BedrockService
from services.mcp_client import get_mcp_tools

logger = logging.getLogger(__name__)

# Cache MCP tools at module level (same pattern as graph.py)
# Tools are fetched once when module loads and indexed by name for quick lookup
_mcp_tools_cache: Dict[str, Any] = {}
_mcp_tools_initialized = False


async def _get_mcp_tools_dict(config: Configuration) -> Dict[str, Any]:
    """Get MCP tools dictionary indexed by tool name.
    
    Uses the same pattern as graph.py - fetches tools once and caches them.
    Tools are indexed by friendly name for O(1) lookup.
    
    Args:
        config: Configuration object
        
    Returns:
        Dictionary mapping tool names to tool objects
    """
    global _mcp_tools_cache, _mcp_tools_initialized
    
    # If tools are already cached, return them
    if _mcp_tools_initialized and _mcp_tools_cache:
        logger.debug(f"_get_mcp_tools_dict: Using cached tools ({len(_mcp_tools_cache)} tools)")
        return _mcp_tools_cache
    
    # Fetch tools from MCP Gateway (same as graph.py)
    logger.info("_get_mcp_tools_dict: Fetching MCP tools from Gateway...")
    tools = await get_mcp_tools(config)
    logger.info(f"_get_mcp_tools_dict: Retrieved {len(tools)} tools from MCP Gateway")
    
    # Index tools by name for O(1) lookup
    _mcp_tools_cache = {tool.name: tool for tool in tools}
    _mcp_tools_initialized = True
    
    logger.info(f"_get_mcp_tools_dict: Cached {len(_mcp_tools_cache)} tools: {list(_mcp_tools_cache.keys())}")
    return _mcp_tools_cache


async def _call_mcp_tool(tool_name: str, arguments: dict, config: Configuration) -> Any:
    """Helper function to call MCP tools.
    
    Uses cached tools dictionary (same pattern as graph.py) for efficient lookup.
    
    Args:
        tool_name: Friendly tool name (e.g., "update_issue_field")
        arguments: Tool arguments
        config: Configuration object
        
    Returns:
        Tool result
    """
    import traceback
    
    logger.info(f"_call_mcp_tool: Attempting to call tool '{tool_name}' with arguments: {arguments}")
    
    try:
        # Get tools dictionary (cached after first call)
        tools_dict = await _get_mcp_tools_dict(config)
        
        # Look up tool by name (O(1) lookup)
        tool = tools_dict.get(tool_name)
        
        if not tool:
            available_tool_names = list(tools_dict.keys())
            logger.error(f"_call_mcp_tool: Tool '{tool_name}' not found. Available tools: {available_tool_names}")
            raise ValueError(f"Tool {tool_name} not found. Available tools: {available_tool_names}")
        
        logger.info(f"_call_mcp_tool: Found tool '{tool_name}' (original name: {tool.metadata.get('_original_name', 'N/A') if hasattr(tool, 'metadata') and tool.metadata else 'N/A'})")
        
        # Invoke the tool
        logger.info(f"_call_mcp_tool: Invoking tool '{tool_name}' with arguments: {arguments}")
        try:
            result = await tool.ainvoke(arguments)
            logger.info(f"_call_mcp_tool: Tool '{tool_name}' invocation successful. Result type: {type(result).__name__}")
            return result
        except Exception as invoke_error:
            logger.error(f"_call_mcp_tool: Error invoking tool '{tool_name}': {type(invoke_error).__name__}: {str(invoke_error)}")
            logger.error(f"_call_mcp_tool: Invoke error traceback:\n{traceback.format_exc()}")
            raise
    except ValueError:
        # Re-raise ValueError as-is (tool not found)
        raise
    except Exception as e:
        logger.error(f"_call_mcp_tool: Unexpected error calling tool '{tool_name}': {type(e).__name__}: {str(e)}")
        logger.error(f"_call_mcp_tool: Full traceback:\n{traceback.format_exc()}")
        
        # Try to extract sub-exception details
        if hasattr(e, '__cause__') and e.__cause__:
            logger.error(f"_call_mcp_tool: Caused by: {type(e.__cause__).__name__}: {str(e.__cause__)}")
        if hasattr(e, '__context__') and e.__context__:
            logger.error(f"_call_mcp_tool: Context: {type(e.__context__).__name__}: {str(e.__context__)}")
        
        raise


async def analyze_summary_node(
    state: CustomerSupportState, config: RunnableConfig
) -> Dict[str, Any]:
    """Analyze summary and description to extract order_no.
    
    This node extracts order_no from summary/description using text_llm.
    
    Args:
        state: Current state containing summary and description
        config: Runtime configuration
        
    Returns:
        Updated state with order_no if found
    """
    cfg = Configuration.from_environment()
    bedrock_service = BedrockService(cfg)
    llm = bedrock_service.get_text_llm()
    
    summary = state.get("summary") or ""
    description = state.get("description") or ""
    combined_text = f"{summary}\n{description}".strip()
    
    if not combined_text:
        logger.info("analyze_summary_node: No summary or description to analyze")
        return {}
    
    # Check if order_no already exists in state
    order_no = state.get("order_no", "")
    if order_no:
        logger.info(f"analyze_summary_node: order_no already exists: {order_no}")
        return {}
    
    # Extract order number from text
    prompt = get_extract_order_number_prompt()
    messages = [HumanMessage(content=f"{combined_text}\n\n{prompt}")]
    
    try:
        ai_msg = await llm.ainvoke(messages)
        
        # Handle case where content might be a list (structured output) or string
        content = ai_msg.content
        if isinstance(content, list):
            if content and isinstance(content[0], dict) and "text" in content[0]:
                content_str = content[0]["text"]
            elif content and isinstance(content[0], str):
                content_str = content[0]
            else:
                content_str = str(content)
        else:
            content_str = str(content)
        
        json_obj = extract_json_from_response(content_str)
        order_no = json_obj.get("orderno", "") or None
        
        if order_no:
            logger.info(f"analyze_summary_node: Extracted order_no: {order_no}")
            return {"order_no": order_no}
        else:
            logger.info("analyze_summary_node: No order_no found in text")
            return {}
    except Exception as e:
        logger.error(f"analyze_summary_node: Error extracting order number: {str(e)}")
        return {}


async def analyze_attachments_node(
    state: CustomerSupportState, config: RunnableConfig
) -> Dict[str, Any]:
    """Analyze attachments to extract transaction_id.
    
    This node downloads attachments (images) and uses vision_llm to extract
    transaction_id from images.
    
    Args:
        state: Current state containing attachments (list of URLs)
        config: Runtime configuration
        
    Returns:
        Updated state with transaction_id if found in attachments
    """
    cfg = Configuration.from_environment()
    bedrock_service = BedrockService(cfg)
    
    # Check if we have attachments
    attachments = state.get("attachments", [])
    if not attachments or len(attachments) == 0:
        logger.info("analyze_attachments_node: No attachments to analyze")
        return {}
    
    # Check if transaction_id already exists in state
    transaction_id = state.get("transaction_id", "")
    if transaction_id:
        logger.info(f"analyze_attachments_node: transaction_id already exists: {transaction_id}")
        return {}
    
    # Prepare prompt for extracting transaction_id
    prompt_text = get_analyze_attachments_prompt()
    human_messages = [{"type": "text", "text": prompt_text}]
    
    # Download and process first attachment
    attachment_url = attachments[0]
    temp_file_path = None
    try:
        logger.info(f"analyze_attachments_node: Downloading attachment from {attachment_url}")
        # Use _call_mcp_tool helper to download attachment via MCP
        # Extract attachment_id from URL first
        import re
        attachment_id_match = re.search(r'/attachment/(?:content/)?(\d+)', attachment_url)
        if attachment_id_match:
            attachment_id = attachment_id_match.group(1)
            logger.info(f"analyze_attachments_node: Extracted attachment_id={attachment_id}, calling MCP tool")
            result = await _call_mcp_tool("download_attachment", {"attachment_id": attachment_id}, cfg)
            
            # Parse result and save to temp file
            import base64
            import tempfile
            import asyncio
            from pathlib import Path
            from langchain_core.messages import ToolMessage
            
            # Handle different result formats (dict, ToolMessage, list)
            result_dict = None
            
            if isinstance(result, dict) and "content_base64" in result:
                # Direct dict format
                result_dict = result
            elif isinstance(result, ToolMessage):
                # ToolMessage object - extract content
                content = result.content
                logger.debug(f"analyze_attachments_node: ToolMessage content type: {type(content).__name__}")
                
                if isinstance(content, str):
                    # Content is a JSON string
                    try:
                        result_dict = json.loads(content)
                    except json.JSONDecodeError:
                        logger.error(f"analyze_attachments_node: Failed to parse ToolMessage content as JSON: {content[:100]}")
                        raise ValueError(f"Failed to parse ToolMessage content as JSON")
                elif isinstance(content, list) and len(content) > 0:
                    # Content is a list of content blocks (LangChain structured format)
                    first_block = content[0]
                    if isinstance(first_block, dict) and first_block.get("type") == "text":
                        text_content = first_block.get("text", "")
                        if text_content:
                            try:
                                result_dict = json.loads(text_content)
                            except json.JSONDecodeError:
                                logger.error(f"analyze_attachments_node: Failed to parse content block text as JSON: {text_content[:100]}")
                                raise ValueError(f"Failed to parse content block text as JSON")
                    elif isinstance(first_block, dict):
                        # Use the dict directly if it looks like our result
                        result_dict = first_block
                else:
                    logger.error(f"analyze_attachments_node: Unexpected ToolMessage content format: {type(content)}")
                    raise ValueError(f"Unexpected ToolMessage content format: {type(content)}")
            elif isinstance(result, list) and len(result) > 0:
                # Result is a list - might be ToolMessage objects or content blocks
                first_item = result[0]
                if isinstance(first_item, ToolMessage):
                    # List of ToolMessage objects - use the first one
                    content = first_item.content
                    if isinstance(content, str):
                        try:
                            result_dict = json.loads(content)
                        except json.JSONDecodeError:
                            logger.error(f"analyze_attachments_node: Failed to parse list[ToolMessage] content as JSON")
                            raise ValueError(f"Failed to parse list[ToolMessage] content as JSON")
                    elif isinstance(content, dict):
                        result_dict = content
                elif isinstance(first_item, dict):
                    # List of dicts - check if it's a content block or direct result
                    if first_item.get("type") == "text" and "text" in first_item:
                        # It's a LangChain content block - parse the text field as JSON
                        text_content = first_item.get("text", "")
                        if text_content:
                            try:
                                result_dict = json.loads(text_content)
                                logger.debug(f"analyze_attachments_node: Parsed JSON from content block text field")
                            except json.JSONDecodeError as e:
                                logger.error(f"analyze_attachments_node: Failed to parse content block text as JSON: {text_content[:100]}")
                                raise ValueError(f"Failed to parse content block text as JSON: {str(e)}")
                    elif "content_base64" in first_item:
                        # Direct result dict
                        result_dict = first_item
                    else:
                        # Unknown dict format - log and try to use it
                        logger.warning(f"analyze_attachments_node: Unknown dict format in list, keys: {list(first_item.keys())}")
                        result_dict = first_item
                else:
                    logger.error(f"analyze_attachments_node: Unexpected list item type: {type(first_item)}")
                    raise ValueError(f"Unexpected list item type: {type(first_item)}")
            else:
                logger.error(f"analyze_attachments_node: Unexpected result type: {type(result)}")
                raise ValueError(f"Unexpected MCP tool result format: {type(result)}")
            
            # Extract file content from parsed result
            if not result_dict or "content_base64" not in result_dict:
                logger.error(f"analyze_attachments_node: Result dict missing 'content_base64' key. Keys: {list(result_dict.keys()) if result_dict else 'None'}")
                raise ValueError(f"Result dict missing 'content_base64' key")
            
            file_content_b64 = result_dict["content_base64"]
            filename = result_dict.get("filename", "attachment")
            file_extension = Path(filename).suffix or '.tmp'
            file_content = base64.b64decode(file_content_b64)
            
            def _create_and_write_temp_file():
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
                temp_path = temp_file.name
                temp_file.close()
                with open(temp_path, 'wb') as f:
                    f.write(file_content)
                return temp_path
            
            temp_file_path = await asyncio.to_thread(_create_and_write_temp_file)
            logger.info(f"analyze_attachments_node: Successfully downloaded attachment via MCP tool: {filename} ({len(file_content)} bytes)")
        else:
            # Fallback to direct download if we can't extract attachment_id
            logger.warning(f"analyze_attachments_node: Could not extract attachment_id, falling back to direct download")
            temp_file_path = await download_attachment(attachment_url, config=None)
        
        # Add image to messages (wrap in asyncio.to_thread to avoid blocking)
        image_data = await asyncio.to_thread(add_image_content, temp_file_path)
        human_messages.append(image_data)
        
        # Invoke vision model
        vision_llm = bedrock_service.get_vision_llm()
        messages = [HumanMessage(content=human_messages)]
        ai_msg = await vision_llm.ainvoke(messages)
        
        # Extract transaction ID from JSON response
        content = ai_msg.content
        if isinstance(content, list):
            if content and isinstance(content[0], dict) and "text" in content[0]:
                content_str = content[0]["text"]
            elif content and isinstance(content[0], str):
                content_str = content[0]
            else:
                content_str = str(content)
        else:
            content_str = str(content)
        
        json_obj = extract_json_from_response(content_str)
        transaction_id = json_obj.get("transactionid", "") or None
        
        if transaction_id:
            logger.info(f"analyze_attachments_node: Extracted transaction_id: {transaction_id}")
            return {"transaction_id": transaction_id}
        else:
            logger.info("analyze_attachments_node: No transaction_id found in image")
            return {}
    except Exception as e:
        logger.error(f"analyze_attachments_node: Error analyzing attachment: {str(e)}")
        return {}
    finally:
        # Clean up temporary file (use asyncio.to_thread to avoid blocking)
        if temp_file_path:
            try:
                from pathlib import Path
                await asyncio.to_thread(Path(temp_file_path).unlink, missing_ok=True)
            except Exception as e:
                logger.warning(f"analyze_attachments_node: Failed to clean up temp file: {str(e)}")


async def update_category_node(
    state: CustomerSupportState, config: RunnableConfig
) -> Dict[str, Any]:
    """Categorize the issue and update category in Jira.
    
    This node:
    1. Uses text_llm to categorize the issue
    2. Updates the category custom field in Jira using update_issue_field tool
    
    Args:
        state: Current state containing issue information
        config: Runtime configuration
        
    Returns:
        Updated state with category set
    """
    issue_no = state.get("issue_no")
    if not issue_no:
        logger.warning("update_category_node: No issue_no in state")
        return {}
    
    cfg = Configuration.from_environment()
    bedrock_service = BedrockService(cfg)
    llm = bedrock_service.get_text_llm()
    
    # Get categorization prompt
    prompt = get_categorization_prompt(state)
    
    # Invoke LLM with prompt
    try:
        ai_msg = await llm.ainvoke([HumanMessage(content=prompt)])
        
        # Extract category from response
        category = extract_text_content(ai_msg.content).strip()
        
        # Validate category is one of the expected values
        valid_categories = ["Transaction", "Delivery", "Refunds", "Other"]
        if category not in valid_categories:
            logger.warning(f"update_category_node: Invalid category '{category}', defaulting to 'Other'")
            category = "Other"
        
        logger.info(f"update_category_node: Determined category: {category}")
        
        # Update category in Jira using MCP tool
        # Use friendly name "category" - jira.py will convert it to customfield_XXXXX
        if cfg.jira_category_field_id:
            try:
                await _call_mcp_tool(
                    "update_issue_field",
                    {
                        "issue_key": issue_no,
                        "field_name": "category",
                        "value": category
                    },
                    cfg
                )
                logger.info(f"update_category_node: Updated category in Jira: {category}")
            except Exception as e:
                logger.error(f"update_category_node: Failed to update category in Jira: {str(e)}")
        else:
            logger.warning("update_category_node: jira_category_field_id not configured, skipping Jira update")
        
        return {"category": category}
    except Exception as e:
        logger.error(f"update_category_node: Error categorizing issue: {str(e)}")
        return {}


async def update_assignee_node(
    state: CustomerSupportState, config: RunnableConfig
) -> Dict[str, Any]:
    """Assign the issue to the configured assignee in Jira.
    
    This node assigns the Jira issue to the configured bot user using
    update_issue_field tool.
    
    Args:
        state: Current state containing issue information
        config: Runtime configuration
        
    Returns:
        Updated state (assignee may be updated)
    """
    cfg = Configuration.from_environment()
    
    issue_no = state.get("issue_no")
    if not issue_no:
        logger.warning("update_assignee_node: No issue_no in state")
        return {}
    
    if not cfg.jira_assignee_username:
        logger.warning("update_assignee_node: jira_assignee_username not configured, skipping assignment")
        return {}
    
    try:
        # Update assignee in Jira using MCP tool
        logger.info(f"update_assignee_node: Calling update_issue_field tool with issue_key={issue_no}, field_name=assignee, value={cfg.jira_assignee_username}")
        result = await _call_mcp_tool(
            "update_issue_field",
            {
                "issue_key": issue_no,
                "field_name": "assignee",
                "value": cfg.jira_assignee_username
            },
            cfg
        )
        logger.info(f"update_assignee_node: MCP tool returned result type: {type(result).__name__}, result: {result}")
        
        # Parse result to check if update was successful
        # Result might be a dict, ToolMessage, or list
        result_dict = None
        if isinstance(result, dict):
            result_dict = result
        elif isinstance(result, list) and len(result) > 0:
            first_item = result[0]
            if isinstance(first_item, dict):
                if first_item.get("type") == "text" and "text" in first_item:
                    # Content block - parse JSON from text field
                    try:
                        result_dict = json.loads(first_item.get("text", ""))
                    except json.JSONDecodeError:
                        result_dict = first_item
                else:
                    result_dict = first_item
        
        # Check if update was successful
        if result_dict:
            if "error" in result_dict:
                error_msg = result_dict.get("error", "Unknown error")
                logger.error(f"update_assignee_node: JIRA update failed: {error_msg}")
                raise Exception(f"JIRA update failed: {error_msg}")
            elif result_dict.get("status") == "success":
                logger.info(f"update_assignee_node: Successfully assigned issue {issue_no} to {cfg.jira_assignee_username} in Jira")
            else:
                logger.warning(f"update_assignee_node: Unexpected result format: {result_dict}")
        else:
            logger.warning(f"update_assignee_node: Could not parse result, assuming success")
        
        return {"assignee": cfg.jira_assignee_username}
    except Exception as e:
        logger.error(f"update_assignee_node: Failed to assign issue: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"update_assignee_node: Full traceback:\n{traceback.format_exc()}")
        # Still update state even if JIRA update fails
        return {"assignee": cfg.jira_assignee_username}


async def create_response_generation_agent(state: CustomerSupportState) -> Any:
    """Create a response generation agent with database tools.
    
    This function creates an agent that:
    1. Has access to find_transaction, find_order, get_transaction_for_order, and get_refund_for_order tools
    2. Uses reasoning LLM to generate a comprehensive response
    3. The agent uses tools to fetch complete JSON objects for transaction, order, and refund
    4. Updates the response in Jira and manages state flags
    
    Args:
        state: Current state containing issue information and identifiers
        
    Returns:
        Compiled agent graph for response generation
    """
    from langchain.agents import create_agent
    
    issue_no = state.get("issue_no")
    if not issue_no:
        logger.warning("create_response_generation_agent: No issue_no in state")
        return None
    
    cfg = Configuration.from_environment()
    bedrock_service = BedrockService(cfg)
    llm = bedrock_service.get_reasoning_llm()
    
    # Get information from state
    category = state.get("category", "N/A")
    summary = state.get("summary", "N/A")
    description = state.get("description", "N/A")
    transaction_id = state.get("transaction_id")
    order_no = state.get("order_no")
    
    # Get system prompt with context (including issue_key)
    prompt = get_response_generation_system_prompt(
        category=category,
        summary=summary,
        description=description,
        issue_key=issue_no,
        transaction_id=transaction_id,
        order_no=order_no
    )
    
    # Get MCP tools for order/transaction queries and JIRA updates
    mcp_tools = await get_mcp_tools(cfg)
    
    # Filter to get the tools we need for response generation
    query_tools = [
        tool for tool in mcp_tools 
        if tool.name in ["find_transaction", "find_order", "get_transaction_for_order", "get_refund_for_order"]
    ]
    
    # Get update_issue_field tool for saving response
    update_tool = [tool for tool in mcp_tools if tool.name == "update_issue_field"]
    
    # Combine all tools: query tools + update tool + custom state tools
    response_tools = query_tools + update_tool + [resetInitiateIssueAnalysisFlag, updateIsInConversationModeFlag]
    
    if not query_tools:
        logger.error("create_response_generation_agent: Required query tools not found. Available tools: " + 
                    ", ".join([t.name for t in mcp_tools]))
        return None
    
    if not update_tool:
        logger.error("create_response_generation_agent: update_issue_field tool not found. Available tools: " + 
                    ", ".join([t.name for t in mcp_tools]))
        return None
    
    logger.info(f"create_response_generation_agent: Creating agent with {len(response_tools)} tools "
                f"({len(query_tools)} query tools, 1 update tool, 2 state tools)")
    
    # Create middleware list - StateUpdateMiddleware is required to update state when tools are called
    middleware = [StateUpdateMiddleware()]
    
    # Create agent with all required tools and middleware
    # The middleware will handle state updates when resetInitiateIssueAnalysisFlag and 
    # updateIsInConversationModeFlag are called
    response_agent = create_agent(
        model=llm,
        tools=response_tools,
        system_prompt=prompt,
        middleware=middleware,
    )
    
    return response_agent


async def update_response_node(
    state: CustomerSupportState, config: RunnableConfig
) -> Dict[str, Any]:
    """Generate response and update in Jira using agent with database tools.
    
    This node creates a response generation agent that will:
    1. Fetch complete details for transaction, order, and refund
    2. Generate a comprehensive response
    3. Reset initiateIssueAnalysis flag to False
    4. Set isInConversationMode flag to True
    5. Update response field in JIRA
    
    The agent handles all the work including the three final steps as instructed in the prompt.
    
    Note: Unlike customer_support_agent which is created at build time and added directly
    via add_node() (so LangGraph auto-invokes it), this agent must be created dynamically
    at runtime because it depends on state values (category, summary, transaction_id, etc.)
    to build its prompt. Therefore, we must manually invoke it here.
    
    Args:
        state: Current state containing issue information and identifiers
        config: Runtime configuration
        
    Returns:
        Dictionary with state updates including messages from the agent
    """
    agent = await create_response_generation_agent(state)
    if agent is None:
        logger.error("update_response_node: Failed to create response generation agent")
        return {}
    
    # Manually invoke the agent - LangGraph doesn't auto-invoke graphs returned from node functions
    # Only graphs added directly via add_node() are auto-invoked
    logger.info("update_response_node: Invoking response generation agent")
    try:
        # Create a state copy with a trigger message to prompt the agent to generate a response
        # The ReAct agent needs a user message to respond to
        trigger_state = state.copy()
        messages = list(trigger_state.get("messages", []))
        
        # Add a trigger message to prompt the agent to generate the response
        # This ensures the agent has something to respond to
        trigger_message = HumanMessage(content="Please generate the customer response now based on the issue analysis.")
        messages.append(trigger_message)
        trigger_state["messages"] = messages
        
        logger.info(f"update_response_node: Invoking agent with {len(messages)} messages in state")
        result = await agent.ainvoke(trigger_state, config)
        
        # Log what we got back
        result_messages = result.get("messages", [])
        logger.info(f"update_response_node: Agent completed. Result has {len(result_messages)} messages")
        logger.info(f"update_response_node: Result keys: {list(result.keys())}")
        
        # Log state updates that should be present
        if "isInConversationMode" in result:
            logger.info(f"update_response_node: isInConversationMode = {result.get('isInConversationMode')}")
        if "initiateIssueAnalysis" in result:
            logger.info(f"update_response_node: initiateIssueAnalysis = {result.get('initiateIssueAnalysis')}")
        if "response" in result:
            logger.info(f"update_response_node: response = {result.get('response')[:100] if result.get('response') else None}...")
        
        if result_messages:
            last_message = result_messages[-1]
            logger.info(f"update_response_node: Last message type: {type(last_message).__name__}, content length: {len(str(last_message.content)) if hasattr(last_message, 'content') else 'N/A'}")
        
        # Extract state updates from the agent result
        # We need to return ALL state updates (flags, response field) plus only NEW messages
        state_updates = {}
        
        # Get the original message count (before we added the trigger)
        original_message_count = len(state.get("messages", []))
        
        # Extract only the new messages added by the agent (excluding our trigger message)
        if "messages" in result:
            # The agent added messages after the trigger, so get everything after original count + 1 (trigger)
            new_messages = result["messages"][original_message_count + 1:]
            state_updates["messages"] = new_messages
            logger.info(f"update_response_node: Extracted {len(new_messages)} new messages from agent")
        else:
            state_updates["messages"] = []
        
        # Extract all other state updates (flags, response field, etc.)
        # These are the state fields that were updated by the middleware via Command objects
        state_fields_to_preserve = [
            "isInConversationMode",
            "initiateIssueAnalysis", 
            "response",
            "issue_no",
            "summary",
            "description",
            "category",
            "assignee",
            "reporter",
            "customer_email",
            "customer_name",
            "transaction_id",
            "order_no",
            "attachments"
        ]
        
        for field in state_fields_to_preserve:
            if field in result:
                # Only include if it's different from the original state (or if it's a new value)
                original_value = state.get(field)
                new_value = result.get(field)
                if new_value != original_value:
                    state_updates[field] = new_value
                    logger.info(f"update_response_node: Including state update: {field} = {new_value}")
        
        logger.info(f"update_response_node: Returning state updates with keys: {list(state_updates.keys())}")
        return state_updates
    except Exception as e:
        logger.error(f"update_response_node: Error invoking agent: {e}", exc_info=True)
        return {}
