# Customer Support Agent

An AI-powered customer support agent built with LangGraph and Amazon Bedrock that automates customer support workflows including triage, issue analysis, and response generation.

## Overview

The Customer Support Agent is a LangGraph-based AI agent that:
- **Triages customer inquiries** by collecting and validating customer information and issue details
- **Retrieves context** from AgentCore Memory to personalize interactions
- **Analyzes issues** by extracting transaction IDs, order numbers, and categorizing issues
- **Generates responses** by fetching complete order/transaction/refund details and crafting comprehensive customer responses
- **Persists conversations** to AgentCore Memory for long-term context

## Features

### Triage Phase
- **Personalized Welcome**: When customer information is available from memory, welcomes customers by name
- **Information Collection**: Collects customer email and issue/ticket number
- **Validation**: Validates customer email against database and verifies issue ownership
- **Dynamic Prompts**: Switches between triage and dialog prompts based on conversation state

### Issue Analysis
- **Summary Analysis**: Extracts order numbers from issue summaries using LLM
- **Attachment Analysis**: Downloads and analyzes JIRA attachments to extract transaction IDs
- **Categorization**: Categorizes issues (Transaction, Delivery, Refunds, Other) and updates JIRA
- **Assignment**: Assigns issues to configured support contacts
- **Response Generation**: Generates comprehensive customer responses with order/transaction/refund details

### Memory Integration
- **Context Retrieval**: Retrieves customer name and email from AgentCore Memory when available
- **Conversation Persistence**: Persists conversation events to AgentCore Memory for long-term context
- **Semantic Search**: Uses semantic facts and user preferences to personalize interactions

### Tool Integration
- **MCP Gateway**: Connects to MCP Gateway for unified access to:
  - Order Management API (find_order, find_transaction, get_refund_for_order)
  - Issue Management API (get_issue, find_customer, update_issue_field)
  - Product Knowledge Base (query_products_kb)
- **Automatic Token Refresh**: OAuth token refresh for MCP Gateway authentication

## Architecture

### Workflow Graph

```
START
  ↓
Retrieve Context (retrieves customer info from memory, injects prompt)
  ↓
Customer Support Agent (triage/dialog agent)
  ↓
  ├─→ Issue Analysis (if initiateIssueAnalysis flag is True)
  │     ├─→ Analyze Summary
  │     ├─→ Analyze Attachments
  │     ├─→ Determine Category
  │     ├─→ Assign Support Contact
  │     └─→ Generate Response
  │
  └─→ Persist Context (persists conversation to memory)
        ↓
      END
```

### State Management

The agent uses `CustomerSupportState` which extends `MessagesState` and includes:
- **Customer Info**: `customer_name`, `customer_email`
- **Issue Info**: `issue_no`, `summary`, `description`, `category`, `assignee`, `reporter`
- **Identifiers**: `transaction_id`, `order_no`
- **Flags**: `isInConversationMode`, `initiateIssueAnalysis`
- **Response**: `response` (generated customer response)

### Prompt System

The agent uses dynamic prompt injection based on conversation state:

1. **Triage Prompt** (`get_customer_support_agent_triage_system_prompt`):
   - Used when `isInConversationMode` is `False`
   - Two scenarios:
     - **Scenario (a)**: Customer info available from context - welcomes by name, validates email, collects issue number
     - **Scenario (b)**: Customer info not available - collects both email and issue number

2. **Dialog Prompt** (`get_customer_support_agent_dialog_system_prompt`):
   - Used when `isInConversationMode` is `True`
   - Includes all available state context (issue details, customer info, identifiers)
   - Enables natural conversation continuation

3. **Response Generation Prompt** (`get_response_generation_system_prompt`):
   - Used during issue analysis to generate customer responses
   - Includes workflow instructions for fetching order/transaction/refund details

## Prerequisites

- Python 3.12+
- AWS CLI configured with appropriate credentials
- Access to:
  - Amazon Bedrock (Claude Sonnet 4, Mistral models)
  - AgentCore Memory (for context retrieval and persistence)
  - MCP Gateway (for tool access)
  - Bedrock Knowledge Base (for product information)
  - JIRA (for issue management)

## Installation

1. **Navigate to the agent directory:**
   ```bash
   cd customer-support-agent
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -e .
   ```

4. **Install LangGraph CLI:**
   ```bash
   pip install "langgraph-cli[inmem]"
   ```

## Configuration

1. **Copy environment template:**
   ```bash
   cp env.example .env
   ```

2. **Configure environment variables in `.env`:**

   **Required:**
   - `AWS_REGION`: AWS region (e.g., `us-west-2`)
   - `AWS_ACCESS_KEY_ID`: AWS access key
   - `AWS_SECRET_ACCESS_KEY`: AWS secret key
   - `MCP_SERVER_URL`: MCP Gateway URL
   - `MCP_COGNITO_CLIENT_ID`: Cognito client ID for MCP Gateway
   - `MCP_COGNITO_CLIENT_SECRET`: Cognito client secret
   - `MCP_COGNITO_TOKEN_ENDPOINT`: Cognito token endpoint
   - `AGENTCORE_MEMORY_ID`: AgentCore Memory resource ID
   - `PRODUCT_KB_ID`: Bedrock Knowledge Base ID

   **Optional:**
   - `LANGSMITH_TRACING`: Enable LangSmith tracing (`true`/`false`)
   - `LANGSMITH_API_KEY`: LangSmith API key
   - `LANGSMITH_PROJECT`: LangSmith project name
   - `GUARDRAIL_ID`: Bedrock Guardrails ID
   - `GUARDRAIL_VERSION`: Guardrails version
   - `JIRA_ASSIGNEE_USERNAME`: Default JIRA assignee
   - `JIRA_CATEGORY_FIELD_ID`: JIRA custom field ID for category
   - `JIRA_RESPONSE_FIELD_ID`: JIRA custom field ID for response

## Usage

### Development with LangGraph Studio

1. **Start LangGraph Studio:**
   ```bash
   langgraph dev
   ```

2. **Access the UI:**
   - Open `http://localhost:8123` in your browser
   - The graph will be visualized with all nodes and edges
   - You can test the agent by sending messages

3. **Test the Agent:**
   - Send a message like "Hi" to start a conversation
   - The agent will retrieve context from memory if available
   - Follow the conversation flow through triage, validation, and issue analysis

### Production Deployment

The agent is designed to be deployed to LangGraph Cloud or similar hosting. See LangGraph documentation for deployment instructions.

## Components

### Core Modules

- **`graph.py`**: Main LangGraph workflow definition
  - `retrieve_context_node`: Retrieves customer context from memory and injects appropriate prompt
  - `create_customer_support_agent`: Creates the main triage/dialog agent
  - `route_after_agent`: Routes to issue analysis or persistence based on flags

- **`issue_analysis.py`**: Issue analysis workflow
  - `analyze_summary_node`: Extracts order numbers from summaries
  - `analyze_attachments_node`: Downloads and analyzes JIRA attachments
  - `update_category_node`: Categorizes issues using LLM
  - `update_assignee_node`: Assigns issues to support contacts
  - `update_response_node`: Generates customer responses

- **`prompts.py`**: Prompt templates
  - Triage prompts (with/without customer context)
  - Dialog prompts (conversation continuation)
  - Response generation prompts
  - Categorization and analysis prompts

- **`state.py`**: State definitions
  - `CustomerSupportState`: Extends `MessagesState` with support-specific fields

- **`tools.py`**: Custom tools
  - `updateIsInConversationModeFlag`: Sets conversation mode flag
  - `updateInitiateIssueAnalysisFlag`: Triggers issue analysis

- **`middleware.py`**: Agent middleware
  - `StateUpdateMiddleware`: Updates state from tool results
  - `KnowledgeBaseIDMiddleware`: Injects knowledge base ID for queries

### Services

- **`services/mcp_client.py`**: MCP Gateway client
  - OAuth token management with automatic refresh
  - Tool discovery and execution
  - Error handling and retries

- **`services/bedrock_service.py`**: Bedrock service wrapper
  - LLM initialization with guardrails
  - Model configuration

- **`services/memory_service.py`**: AgentCore Memory service
  - Memory retrieval (semantic facts, preferences)
  - Event persistence
  - Async operations with proper error handling

## Integration

### MCP Gateway

The agent connects to the MCP Gateway to access:
- **Order Management API**: Order and transaction queries
- **Issue Management API**: JIRA issue operations
- **Product Knowledge Base**: Product information queries

### AgentCore Memory

- **Context Retrieval**: Retrieves customer name and email from semantic memory
- **Event Persistence**: Persists conversation events for long-term context
- **Session Management**: Uses actor_id and session_id for memory organization

### Bedrock Knowledge Base

- **Product Queries**: Uses `query_products_kb` tool to answer product-related questions
- **Knowledge Base ID**: Injected via middleware for automatic tool configuration

## Development

### Project Structure

```
customer-support-agent/
├── src/
│   ├── agent/
│   │   ├── graph.py              # Main workflow graph
│   │   ├── issue_analysis.py     # Issue analysis nodes
│   │   ├── prompts.py            # Prompt templates
│   │   ├── state.py              # State definitions
│   │   ├── tools.py              # Custom tools
│   │   └── middleware.py         # Agent middleware
│   └── services/
│       ├── mcp_client.py         # MCP Gateway client
│       ├── bedrock_service.py    # Bedrock service
│       └── memory_service.py      # AgentCore Memory service
├── langgraph.json                # LangGraph configuration
├── pyproject.toml                # Python project configuration
├── env.example                   # Environment variable template
└── README.md                     # This file
```

### Testing

Test the agent using LangGraph Studio:
1. Start the dev server: `langgraph dev`
2. Send test messages through the UI
3. Monitor the graph execution and state updates
4. Check logs for debugging information

### Debugging

- **LangSmith**: Enable tracing to see detailed execution logs
- **Logs**: Check console output for node execution and state updates
- **State Inspection**: Use LangGraph Studio to inspect state at each node

## Troubleshooting

### Agent not retrieving context
- Verify `AGENTCORE_MEMORY_ID` is set correctly
- Check that `actor_id` is provided in the config
- Ensure memory records exist for the actor

### Tool calls failing
- Verify MCP Gateway credentials are correct
- Check MCP Gateway URL is accessible
- Ensure OAuth token refresh is working

### Response generation empty
- Check that issue analysis completed successfully
- Verify transaction/order IDs were extracted
- Ensure response was saved to state via `update_issue_field`

## Related Documentation

- **Main README**: `../README.md` - Overall project structure and deployment
- **MCP Gateway**: `../mcp-gateway/README.md` - Gateway setup and configuration
- **AgentCore Memory**: `../shared-infra/README.md` - Memory resource setup
