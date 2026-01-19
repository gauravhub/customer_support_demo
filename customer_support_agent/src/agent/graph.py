"""Customer Support Agent Graph.

This graph uses create_agent as a subgraph node to handle customer conversations.
The agent has access to MCP tools for database operations.

The agent is created as a subgraph so it appears expandable in LangGraph Studio.
"""

import asyncio
import logging
from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END, MessagesState

from agent.state import CustomerSupportState
from agent.configuration import Configuration
from agent.middleware import KnowledgeBaseIDMiddleware
from agent.persist_ltm import get_persist_ltm_node
from services.bedrock import BedrockService
from services.mcp_client import get_mcp_tools


logger = logging.getLogger(__name__)


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
    try:
        tools = await get_mcp_tools(cfg)
    except Exception as exc:
        logger.error(
            "Failed to load MCP tools, continuing without tools: %s",
            exc,
            exc_info=exc,
        )
        if isinstance(exc, BaseExceptionGroup):
            for idx, sub_exc in enumerate(exc.exceptions, start=1):
                logger.error(
                    "MCP tools sub-exception %s: %s",
                    idx,
                    sub_exc,
                    exc_info=sub_exc,
                )
        tools = []
    
    # Create middleware to inject knowledgeBaseId into query_products_kb tool
    middleware = []
    if cfg.product_kb_id:
        middleware.append(KnowledgeBaseIDMiddleware(kb_id=cfg.product_kb_id))
    
    # Create agent (returns a compiled graph)
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt="You are a helpful customer support agent. Assist customers with their inquiries using the available tools.",
        middleware=middleware if middleware else None
    )
    
    return agent


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

# Add the customer_support_agent as a subgraph node
# This makes it appear as an expandable subgraph in LangGraph Studio
builder.add_node("Support Agent", customer_support_agent_subgraph)
builder.add_node("Persist LTM", get_persist_ltm_node())

# Add edges
builder.add_edge(START, "Support Agent")
builder.add_edge("Support Agent", "Persist LTM")
builder.add_edge("Persist LTM", END)

# Compile the graph
graph = builder.compile()
