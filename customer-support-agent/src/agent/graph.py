"""Customer Support Agent Graph.

This graph uses create_agent as a subgraph node to handle customer conversations.
The agent has access to MCP tools for database operations.

The agent is created as a subgraph so it appears expandable in LangGraph Studio.
"""

import asyncio
import logging
import re
from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.runnables import RunnableConfig
from typing import Literal

from agent.state import CustomerSupportState
from agent.configuration import Configuration
from agent.middleware import KnowledgeBaseIDMiddleware, StateUpdateMiddleware
from agent.persist_ltm import AgentCoreMemoryService, get_persist_ltm_node
from agent.prompts import (
    get_customer_support_agent_triage_system_prompt,
    get_customer_support_agent_dialog_system_prompt
)
from langchain_core.messages import SystemMessage
from agent.tools import updateIsInConversationModeFlag, updateInitiateIssueAnalysisFlag
from agent.issue_analysis import (
    analyze_summary_node,
    analyze_attachments_node,
    update_category_node,
    update_assignee_node,
    update_response_node,
)
from services.bedrock import BedrockService
from services.mcp_client import get_mcp_tools


logger = logging.getLogger(__name__)


async def retrieve_context_node(
    state: CustomerSupportState, config: RunnableConfig
) -> dict:
    """Retrieve context from AgentCore Memory and inject appropriate system prompt.
    
    This node:
    1. Retrieves semantic facts and user preferences from AgentCore Memory
       to pre-populate customer information (username and email) when:
       - actor_id is available in config
       - isInConversationMode is False (not in an active conversation)
    2. Injects the appropriate system prompt based on isInConversationMode:
       - Dialog prompt if isInConversationMode is True
       - Triage prompt if isInConversationMode is False
    
    Args:
        state: Current state
        config: Runtime configuration (should contain actor_id in configurable)
        
    Returns:
        Dictionary with state updates including customer_email and customer_name if found,
        and updated messages with the appropriate SystemMessage
    """
    logger.info("retrieve_context_node: Starting context retrieval and prompt injection")
    
    # Get actor_id from configurable
    configurable = config.get("configurable", {}) if config else {}
    actor_id = configurable.get("actor_id")
    
    # Check if we should retrieve context
    is_in_conversation_mode = state.get("isInConversationMode", False)
    
    # Initialize state_updates - will be populated with memory retrieval results if applicable
    state_updates = {}
    
    if not actor_id:
        logger.info("retrieve_context_node: No actor_id in config, skipping memory retrieval")
    elif is_in_conversation_mode:
        logger.info("retrieve_context_node: Already in conversation mode, skipping memory retrieval")
    else:
        logger.info(f"retrieve_context_node: Retrieving context for actor_id={actor_id}")
        
        try:
            cfg = Configuration.from_environment()
            memory_service = AgentCoreMemoryService(cfg)
            
            # Query semantic facts and user preferences for username and email
            queries = [
                "user's name or username",
                "user's email address",
                "customer email",
                "customer name"
            ]
            
            found_email = False
            found_name = False
            
            # Try each query to find username and email
            for query in queries:
                if found_email and found_name:
                    break
                
                try:
                    memories = await memory_service.retrieve_memory(
                        actor_id=actor_id,
                        query=query,
                        memory_types=["semantic", "preferences"],
                        max_results=5
                    )
                    
                    # Helper function to extract text content from memory item
                    def extract_content(memory_item):
                        """Extract text content from memory item, handling different structures.
                        
                        MemoryRecordSummary structure:
                        {
                            "content": { ... },  # Content object (may have text, structured data, etc.)
                            "memoryRecordId": "...",
                            "score": ...,
                            ...
                        }
                        """
                        # Try different possible structures
                        if isinstance(memory_item, str):
                            return memory_item.lower()
                        if isinstance(memory_item, dict):
                            # Try content object (MemoryRecordSummary structure)
                            if "content" in memory_item:
                                content_obj = memory_item["content"]
                                if isinstance(content_obj, dict):
                                    # Try content.text
                                    if "text" in content_obj:
                                        return str(content_obj["text"]).lower()
                                    # Try content.value
                                    if "value" in content_obj:
                                        return str(content_obj["value"]).lower()
                                    # Try content.fact or content.preference (semantic/preferences strategies)
                                    if "fact" in content_obj:
                                        return str(content_obj["fact"]).lower()
                                    if "preference" in content_obj:
                                        return str(content_obj["preference"]).lower()
                                    # If content is a simple dict, try to stringify it
                                    if len(content_obj) == 1:
                                        return str(list(content_obj.values())[0]).lower()
                                elif isinstance(content_obj, str):
                                    return content_obj.lower()
                            # Try direct text field
                            if "text" in memory_item:
                                return str(memory_item["text"]).lower()
                            # Try value field
                            if "value" in memory_item:
                                return str(memory_item["value"]).lower()
                            # Try fact or preference fields directly
                            if "fact" in memory_item:
                                return str(memory_item["fact"]).lower()
                            if "preference" in memory_item:
                                return str(memory_item["preference"]).lower()
                        return ""
                
                    # Process semantic memories
                    for memory_item in memories.get("semantic", []):
                        content = extract_content(memory_item)
                        if not content:
                            continue
                        
                        # Look for email address
                        if not found_email and ("@" in content or "email" in content):
                            # Try to extract email from content
                            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                            emails = re.findall(email_pattern, content, re.IGNORECASE)
                            if emails:
                                state_updates["customer_email"] = emails[0]
                                found_email = True
                                logger.info(f"retrieve_context_node: Found email from semantic memory: {emails[0]}")
                        
                        # Look for name/username
                        if not found_name and ("name" in content or "username" in content):
                            # Try to extract name - look for patterns like "name is X" or "username is X"
                            name_patterns = [
                                r"name is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                                r"username is\s+([A-Za-z0-9_]+)",
                                r"called\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                                r"user\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                            ]
                            for pattern in name_patterns:
                                matches = re.findall(pattern, content, re.IGNORECASE)
                                if matches:
                                    # Capitalize the extracted name properly (e.g., "morgan taylor" -> "Morgan Taylor")
                                    extracted_name = matches[0].title()
                                    state_updates["customer_name"] = extracted_name
                                    found_name = True
                                    logger.info(f"retrieve_context_node: Found name from semantic memory: {extracted_name}")
                                    break
                    
                    # Process user preference memories
                    for memory_item in memories.get("preferences", []):
                        content = extract_content(memory_item)
                        if not content:
                            continue
                        
                        # Look for email address
                        if not found_email and ("@" in content or "email" in content):
                            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                            emails = re.findall(email_pattern, content, re.IGNORECASE)
                            if emails:
                                state_updates["customer_email"] = emails[0]
                                found_email = True
                                logger.info(f"retrieve_context_node: Found email from preferences: {emails[0]}")
                        
                        # Look for name/username
                        if not found_name and ("name" in content or "username" in content):
                            name_patterns = [
                                r"name is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                                r"username is\s+([A-Za-z0-9_]+)",
                                r"called\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                                r"user\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                            ]
                            for pattern in name_patterns:
                                matches = re.findall(pattern, content, re.IGNORECASE)
                                if matches:
                                    # Capitalize the extracted name properly (e.g., "morgan taylor" -> "Morgan Taylor")
                                    extracted_name = matches[0].title()
                                    state_updates["customer_name"] = extracted_name
                                    found_name = True
                                    logger.info(f"retrieve_context_node: Found name from preferences: {extracted_name}")
                                    break
                
                except Exception as e:
                    logger.warning(f"retrieve_context_node: Error querying memory with query '{query}': {e}")
                    continue
            
            if state_updates:
                logger.info(f"retrieve_context_node: Retrieved context: {list(state_updates.keys())}")
            else:
                logger.info("retrieve_context_node: No customer information found in memory")
            
        except Exception as e:
            logger.error(f"retrieve_context_node: Error retrieving context from AgentCore Memory: {e}", exc_info=True)
            state_updates = {}
    
    # Now inject the appropriate system prompt based on state
    # Update state with any retrieved context first (for prompt personalization)
    updated_state = {**state, **state_updates}
    
    is_in_conversation_mode = updated_state.get("isInConversationMode", False)
    customer_email = updated_state.get("customer_email")
    customer_name = updated_state.get("customer_name")
    
    # Select the appropriate prompt
    if is_in_conversation_mode:
        logger.info("retrieve_context_node: Using dialog system prompt (isInConversationMode=True)")
        system_prompt = get_customer_support_agent_dialog_system_prompt(
            customer_name=updated_state.get("customer_name"),
            customer_email=updated_state.get("customer_email"),
            issue_no=updated_state.get("issue_no"),
            summary=updated_state.get("summary"),
            description=updated_state.get("description"),
            category=updated_state.get("category"),
            transaction_id=updated_state.get("transaction_id"),
            order_no=updated_state.get("order_no"),
            assignee=updated_state.get("assignee"),
            reporter=updated_state.get("reporter")
        )
    else:
        logger.info(
            f"retrieve_context_node: Using triage system prompt (isInConversationMode=False, "
            f"customer_name={customer_name}, customer_email={customer_email})"
        )
        system_prompt = get_customer_support_agent_triage_system_prompt(
            customer_name=customer_name,
            customer_email=customer_email
        )
    
    # Get current messages
    messages = list(updated_state.get("messages", []))
    
    # Remove any existing SystemMessage
    messages = [msg for msg in messages if not isinstance(msg, SystemMessage)]
    
    # Add the new SystemMessage at the beginning
    system_message = SystemMessage(content=system_prompt)
    messages.insert(0, system_message)
    
    logger.info(f"retrieve_context_node: Injected system prompt (length={len(system_prompt)} chars)")
    
    # Return both state updates and updated messages
    state_updates["messages"] = messages
    return state_updates


def create_issue_analysis_subgraph():
    """Create a subgraph for issue analysis workflow.
    
    This subgraph contains the following nodes in sequence:
    1. Analyze Summary - Extract order_no from summary/description
    2. Analyze Attachments - Download and analyze attachments to extract transaction_id
    3. Determine Category - Categorize issue and update in Jira
    4. Assign Support Contact - Assign issue to configured assignee
    5. Generate Response - (Placeholder, to be implemented later)
    
    Returns:
        Compiled subgraph for issue analysis
    """
    analysis_builder = StateGraph(CustomerSupportState)
    
    # Add nodes in the correct order
    analysis_builder.add_node("Analyze Summary", analyze_summary_node)
    analysis_builder.add_node("Analyze Attachments", analyze_attachments_node)
    analysis_builder.add_node("Determine Category", update_category_node)
    analysis_builder.add_node("Assign Support Contact", update_assignee_node)
    analysis_builder.add_node("Generate Response", update_response_node)
    
    # Add edges in sequence
    analysis_builder.add_edge(START, "Analyze Summary")
    analysis_builder.add_edge("Analyze Summary", "Analyze Attachments")
    analysis_builder.add_edge("Analyze Attachments", "Determine Category")
    analysis_builder.add_edge("Determine Category", "Assign Support Contact")
    analysis_builder.add_edge("Assign Support Contact", "Generate Response")
    analysis_builder.add_edge("Generate Response", END)
    
    return analysis_builder.compile()

async def create_customer_support_agent():
    """Create a customer support agent with MCP tools.

    This function creates a customer_support_agent using create_agent,
    which returns a compiled graph. The agent is configured with:
    - Reasoning LLM (Claude Sonnet 4) with guardrails
    - MCP tools from the MCP Gateway with automatic token refresh

    Tokens are automatically refreshed via OAuthTokenAuth when they expire.

    Note: The system prompt is injected dynamically via inject_prompt_node
    based on isInConversationMode and customer information in state.

    Returns:
        Compiled graph (customer_support_agent) that can be used as a subgraph node
    """
    cfg = Configuration.from_environment()
    
    # Get LLM with guardrails
    llm = BedrockService(cfg).get_reasoning_llm()
    
    # Get tools from MCP Gateway (automatic token refresh via OAuthTokenAuth)
    mcp_tools = await get_mcp_tools(cfg)
    
    # Add custom tools
    custom_tools = [updateIsInConversationModeFlag, updateInitiateIssueAnalysisFlag]
    
    # Combine MCP tools and custom tools
    tools = mcp_tools + custom_tools
    
    # Create middleware list
    # Order matters: StateUpdateMiddleware should be after KnowledgeBaseIDMiddleware
    # so it can see tool results after execution
    middleware = [
        KnowledgeBaseIDMiddleware(kb_id=cfg.product_kb_id),
        StateUpdateMiddleware(),
    ]
    
    # Create agent with a minimal placeholder system prompt
    # The actual prompt will be injected dynamically by inject_prompt_node based on state
    # We use a placeholder here because create_agent requires a system_prompt parameter
    # inject_prompt_node will replace any SystemMessage with the correct one based on isInConversationMode
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt="You are a customer support agent.",  # Placeholder, will be replaced by inject_prompt_node
        middleware=middleware
    )
    
    return agent



def route_after_agent(state: CustomerSupportState) -> Literal["Issue Analysis", "Persist Context"]:
    """Route workflow based on initiateIssueAnalysis flag.
    
    Args:
        state: Current state
        
    Returns:
        "Issue Analysis" if initiateIssueAnalysis is True, otherwise "Persist Context"
    """
    initiate_issue_analysis = state.get("initiateIssueAnalysis", False)
    
    if initiate_issue_analysis:
        logger.info("Routing to Issue Analysis: initiateIssueAnalysis is True")
        return "Issue Analysis"
    else:
        logger.info("Routing to Persist Context: initiateIssueAnalysis is False")
        return "Persist Context"

# Create the customer_support_agent subgraph
# This is created at build time so LangGraph Studio can visualize it as an expandable subgraph
# Use asyncio.run() to execute the async function at module level
customer_support_agent_subgraph = asyncio.run(create_customer_support_agent())

# Create the main graph builder
# Use MessagesState as input_schema so only 'messages' is required in LangGraph Studio
# All other fields in CustomerSupportState are optional and can be populated during execution
builder = StateGraph(
    CustomerSupportState,
    input_schema=MessagesState  # Only 'messages' field is required in the UI
)

# Create issue analysis subgraph
issue_analysis_subgraph = create_issue_analysis_subgraph()

# Add the customer_support_agent as a subgraph node
# This makes it appear as an expandable subgraph in LangGraph Studio
builder.add_node("Retrieve Context", retrieve_context_node)
builder.add_node("Customer Support Agent", customer_support_agent_subgraph)
builder.add_node("Persist Context", get_persist_ltm_node())
builder.add_node("Issue Analysis", issue_analysis_subgraph)

# Add edges
builder.add_edge(START, "Retrieve Context")
builder.add_edge("Retrieve Context", "Customer Support Agent")

# Add conditional edge from Customer Support Agent based on initiateIssueAnalysis flag
builder.add_conditional_edges(
    "Customer Support Agent",
    route_after_agent,
    {
        "Issue Analysis": "Issue Analysis",
        "Persist Context": "Persist Context"
    }
)

# Add edge from Issue Analysis to Persist Context (after analysis, persist to memory)
builder.add_edge("Issue Analysis", "Persist Context")
builder.add_edge("Persist Context", END)

# Compile the graph
graph = builder.compile()
