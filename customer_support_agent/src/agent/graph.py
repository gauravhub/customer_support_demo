"""Customer Support Agent Graph.

This graph uses create_agent as a subgraph node to handle customer conversations.
The agent has access to MCP tools for database operations.

The agent is created as a subgraph so it appears expandable in LangGraph Studio.
"""

import asyncio
import logging
from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.runnables import RunnableConfig
from typing import Literal

from agent.state import CustomerSupportState
from agent.configuration import Configuration
from agent.middleware import KnowledgeBaseIDMiddleware, StateUpdateMiddleware
from agent.persist_ltm import get_persist_ltm_node
from agent.prompts import get_customer_support_agent_triage_system_prompt
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
    """Retrieve context node (placeholder).
    
    This node can be used to retrieve context before the customer support agent.
    
    Args:
        state: Current state
        config: Runtime configuration
        
    Returns:
        Empty dict (no state updates)
    """
    logger.info("retrieve_context_node: Retrieving context")
    return {}


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
    
    # Get consolidated system prompt that handles welcome, information collection/validation, and ongoing conversation
    system_prompt = get_customer_support_agent_triage_system_prompt()
    
    # Create agent (returns a compiled graph)
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
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
