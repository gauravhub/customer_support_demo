"""Persist the latest conversation turn to AgentCore Memory."""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from agent.configuration import Configuration
from agent.state import CustomerSupportState


logger = logging.getLogger(__name__)


class AgentCoreMemoryService:
    """Service for interacting with Amazon Bedrock AgentCore Memory."""

    @staticmethod
    def _sanitize_id(identifier: str) -> str:
        """Sanitize an identifier to match AgentCore Memory ID pattern."""
        if not identifier:
            return identifier

        sanitized = identifier.replace("@", "-at-").replace(".", "-")

        sanitized = re.sub(r"[^a-zA-Z0-9\-_/:]", "-", sanitized)

        if sanitized and not sanitized[0].isalnum():
            sanitized = "id-" + sanitized

        return sanitized

    def __init__(self, config: Configuration):
        self.config = config
        self.memory_id = config.agentcore_memory_id
        self.aws_region = os.environ.get("AWS_REGION", "us-west-2")

        if not self.memory_id:
            raise ValueError(
                "AgentCore Memory ID is not configured. Set AGENTCORE_MEMORY_ID environment variable."
            )

        self.client = boto3.client("bedrock-agentcore", region_name=self.aws_region)

    async def retrieve_memory(
        self,
        actor_id: str,
        query: str,
        memory_types: Optional[List[str]] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """Retrieve memories from AgentCore Memory.
        
        Args:
            actor_id: Actor ID to retrieve memories for
            query: Query string to search for in memories
            memory_types: List of memory types to retrieve (e.g., ["semantic", "preferences"])
                         If None, retrieves all available memory types
            max_results: Maximum number of results to return per memory type
            
        Returns:
            Dictionary with retrieved memories organized by memory type
        """
        if not actor_id:
            raise ValueError("actor_id is required")
        
        if not query:
            raise ValueError("query is required")
        
        sanitized_actor_id = self._sanitize_id(actor_id)
        
        # Default to semantic and preferences if not specified
        if memory_types is None:
            memory_types = ["semantic", "preferences"]
        
        results = {}
        
        try:
            for memory_type in memory_types:
                # Build namespace based on memory type
                if memory_type == "semantic":
                    namespace = f"/strategy/semantic/actor/{sanitized_actor_id}"
                elif memory_type == "preferences":
                    namespace = f"/strategy/preferences/actor/{sanitized_actor_id}"
                else:
                    logger.warning(f"Unknown memory type: {memory_type}, skipping")
                    continue
                
                try:
                    # Wrap synchronous boto3 call in asyncio.to_thread to avoid blocking
                    def _retrieve_memory_records():
                        """Synchronous helper function to call boto3 API."""
                        return self.client.retrieve_memory_records(
                            memoryId=self.memory_id,
                            namespace=namespace,
                            searchCriteria={
                                "searchQuery": query,
                                "topK": max_results,
                            }
                        )
                    
                    # Run the blocking call in a separate thread
                    response = await asyncio.to_thread(_retrieve_memory_records)
                    
                    # Extract memory records from response
                    # The response contains 'memoryRecordSummaries' field
                    items = response.get("memoryRecordSummaries", [])
                    if not items and "items" in response:
                        items = response.get("items", [])
                    results[memory_type] = items
                    logger.info(
                        f"Retrieved {len(results[memory_type])} {memory_type} memories "
                        f"for actor {sanitized_actor_id} with query: {query}"
                    )
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "")
                    # If namespace doesn't exist or no memories found, that's okay
                    if error_code in ["ResourceNotFoundException", "ValidationException"]:
                        logger.debug(
                            f"No {memory_type} memories found for actor {sanitized_actor_id}: {e}"
                        )
                    else:
                        logger.warning(
                            f"Failed to retrieve {memory_type} memories for actor {sanitized_actor_id}: {e}"
                        )
                    results[memory_type] = []
            
            return results
        except Exception as e:
            raise RuntimeError(f"Failed to retrieve memories from AgentCore Memory: {e}") from e

    async def create_event(
        self,
        actor_id: str,
        session_id: str,
        messages: List[Dict[str, str]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not actor_id or not session_id:
            raise ValueError("actor_id and session_id are required")

        if not messages or not isinstance(messages, list):
            raise ValueError("messages must be a non-empty list")

        sanitized_actor_id = self._sanitize_id(actor_id)
        sanitized_session_id = self._sanitize_id(session_id)

        for msg in messages:
            if not isinstance(msg, dict) or "content" not in msg or "role" not in msg:
                raise ValueError("Each message must be a dict with 'content' and 'role' keys")

        payload = []
        for msg in messages:
            payload.append(
                {
                    "conversational": {
                        "content": {"text": msg["content"]},
                        "role": msg["role"].upper(),
                    }
                }
            )

        try:
            # boto3 expects datetime.datetime object, not timestamp
            event_timestamp = datetime.utcnow()
            params = {
                "memoryId": self.memory_id,
                "actorId": sanitized_actor_id,
                "sessionId": sanitized_session_id,
                "payload": payload,
                "eventTimestamp": event_timestamp,
            }

            if metadata:
                # Metadata values must be wrapped in MetadataValue format
                # According to API, MetadataValue is a union with stringValue
                formatted_metadata = {}
                for key, value in metadata.items():
                    formatted_metadata[key] = {"stringValue": str(value)}
                params["metadata"] = formatted_metadata

            # Wrap synchronous boto3 call in asyncio.to_thread to avoid blocking
            def _create_event():
                """Synchronous helper function to call boto3 API."""
                return self.client.create_event(**params)
            
            # Run the blocking call in a separate thread
            response = await asyncio.to_thread(_create_event)
            return response
        except ClientError as e:
            raise RuntimeError(f"Failed to create event in AgentCore Memory: {e}") from e


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if text:
                    parts.append(text)
        return "\n".join(parts)
    return str(content)


def _message_role(message: Any) -> Optional[str]:
    if isinstance(message, HumanMessage):
        return "USER"
    if isinstance(message, AIMessage):
        return "ASSISTANT"
    if isinstance(message, ToolMessage):
        return "TOOL"
    if isinstance(message, SystemMessage):
        return None
    return None


def _extract_turn_messages(messages: List[Any]) -> List[Any]:
    if not messages:
        return []
    start_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            start_idx = i
            break
    if start_idx is None:
        return []
    return messages[start_idx:]


def get_persist_ltm_node():
    """Return a node that persists the latest turn to AgentCore Memory."""

    async def persist_ltm(state: CustomerSupportState, config: RunnableConfig | None) -> Dict[str, Any]:
        messages = state.get("messages", [])
        turn_messages = _extract_turn_messages(messages)
        if not turn_messages:
            return {}

        configurable = config.get("configurable", {}) if config else {}
        actor_id = configurable.get("actor_id")
        session_id = configurable.get("thread_id")
        if not actor_id or not session_id:
            logger.warning(
                "Skipping AgentCore Memory persistence: missing actor_id or session_id (actor_id=%s, session_id=%s)",
                actor_id,
                session_id,
            )
            return {}

        payload_messages: List[Dict[str, str]] = []
        for msg in turn_messages:
            role = _message_role(msg)
            if not role:
                continue
            content = _content_to_text(getattr(msg, "content", ""))
            if content:
                payload_messages.append({"content": content, "role": role})

        if not payload_messages:
            return {}

        metadata: Dict[str, Any] = {"turn_message_count": len(payload_messages)}
        start_msg_id = getattr(turn_messages[0], "id", None)
        if start_msg_id:
            metadata["turn_start_message_id"] = start_msg_id

        event_payload = {
            "actorId": actor_id,
            "sessionId": session_id,
            "messages": payload_messages,
            "metadata": metadata,
        }
        logger.info(
            "Persisting AgentCore Memory event actor_id=%s session_id=%s payload=%s",
            actor_id,
            session_id,
            json.dumps(event_payload, default=str),
        )

        try:
            cfg = Configuration.from_environment()
            memory_service = AgentCoreMemoryService(cfg)
            response = await memory_service.create_event(
                actor_id=actor_id,
                session_id=session_id,
                messages=payload_messages,
                metadata=metadata,
            )
            logger.info(
                "Successfully persisted event to AgentCore Memory: eventId=%s",
                response.get("eventId", "unknown")
            )
        except Exception as e:
            # Persistence errors shouldn't break the main flow, but we should log them
            logger.error(
                "Failed to persist event to AgentCore Memory: actor_id=%s session_id=%s error=%s",
                actor_id,
                session_id,
                str(e),
                exc_info=True
            )
            return {}

        return {}

    return persist_ltm
