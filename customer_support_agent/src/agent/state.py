"""State definitions for the customer support agent.

This module defines the state structure that flows through the LangGraph workflow.
State holds all the data that nodes can read and write during execution.
"""

from typing import Annotated, Optional
import operator

from langgraph.graph import MessagesState


class CustomerSupportState(MessagesState):
    """State for customer support workflow.
    
    Extends MessagesState to provide built-in message handling.
    All fields here can be read/written by graph nodes.
    
    Note: Fields are kept flat (not nested) for simplicity with LangGraph state updates.
    Conceptually, the following fields form a "Jira Ticket" group:
    - issue_no, summary, description, attachments, category, response, assignee, reporter
    
    Note: Token usage tracking is handled automatically by LangSmith observability.
    No need to manually track usage in state - LangSmith captures all LLM metrics.
    
    Fields:
    - issue_no: Support issue/ticket number (e.g., "AS-5", "64", etc.)
    - summary: Ticket title/summary
    - description: Ticket description/body
    - attachments: List of local file paths (populated from Jira ticket downloads)
    - category: Ticket category (Transaction, Delivery, Refunds, Other)
    - response: Generated response to customer (written back to Jira)
    - assignee: Current assignee of the ticket (email or user ID, can be updated during workflow)
    - reporter: Reporter email address (person who created the issue)
    - transaction_id: Extracted transaction ID (from ticket content)
    - order_no: Extracted order number (from ticket content)
    """
    # Jira Ticket fields (grouped conceptually)
    # These are Optional because they may not be available until ticket is fetched or created
    issue_no: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    attachments: Annotated[list[str], operator.add] = []  # Local file paths
    category: Optional[str] = None
    response: Optional[str] = None  # Written back to Jira custom field
    assignee: Optional[str] = None  # Current assignee (email/user ID), can be updated during workflow
    reporter: Optional[str] = None  # Reporter email address (person who created the issue)
    
    # Customer information (collected at start of conversation)
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    
    # Extracted workflow fields (from ticket content)
    transaction_id: Optional[str] = None
    order_no: Optional[str] = None
