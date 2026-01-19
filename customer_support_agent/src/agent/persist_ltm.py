"""Persist the latest conversation turn to AgentCore Memory."""

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

    def create_event(
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
            event_timestamp = datetime.utcnow()
            params = {
                "memoryId": self.memory_id,
                "actorId": sanitized_actor_id,
                "sessionId": sanitized_session_id,
                "payload": payload,
                "eventTimestamp": event_timestamp,
            }

            if metadata:
                params["metadata"] = metadata

            response = self.client.create_event(**params)
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
            AgentCoreMemoryService(cfg).create_event(
                actor_id=actor_id,
                session_id=session_id,
                messages=payload_messages,
                metadata=metadata,
            )
        except Exception:
            # Persistence errors shouldn't break the main flow.
            return {}

        return {}

    return persist_ltm
