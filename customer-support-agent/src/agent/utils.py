"""Utility functions for the customer support agent.

This module contains helper functions used throughout the workflow.
"""

import base64
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse
import tempfile
import httpx

logger = logging.getLogger(__name__)


def clean_json_string(json_string: str) -> str:
    """Clean JSON string from LLM response by removing markdown code blocks.
    
    Removes triple backticks and 'json' identifier that LLMs often add
    when returning JSON responses.
    
    Args:
        json_string: Raw JSON string from LLM (may include markdown formatting)
        
    Returns:
        Cleaned JSON string ready for parsing
        
    Example:
        Input: "```json\\n{\"key\": \"value\"}\\n```"
        Output: "{\"key\": \"value\"}"
    """
    # Pattern to match ```json\n...\n``` blocks
    pattern = r'```json\n(.*?)```'
    cleaned_string = re.search(pattern, json_string, flags=re.DOTALL)
    
    if cleaned_string:
        return cleaned_string.group(1).strip()
    return json_string.strip()


def get_image_format(image_path: str) -> str:
    """Get image format/MIME type from file extension.
    
    Args:
        image_path: Path to image file
        
    Returns:
        Image format string (e.g., 'jpeg', 'png', 'gif')
        
    Note:
        Converts 'jpg' to 'jpeg' for MIME type consistency
    """
    file_extension = Path(image_path).suffix.lower().lstrip('.')
    if file_extension == 'jpg':
        file_extension = 'jpeg'
    return file_extension


def add_image_content(image_path: str) -> Dict[str, Any]:
    """Read image file and convert to base64 format for vision model input.
    
    Args:
        image_path: Path to image file
        
    Returns:
        Dictionary with image data in format expected by vision models:
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "<base64_encoded_data>"
            }
        }
        
    Raises:
        FileNotFoundError: If image file doesn't exist
        IOError: If image file cannot be read
    """
    image_path_obj = Path(image_path)
    if not image_path_obj.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    with open(image_path, 'rb') as image_file:
        image_bytes = image_file.read()
        base64_encoded = base64.b64encode(image_bytes).decode('utf-8')
    
    image_format = get_image_format(image_path)
    media_type = f"image/{image_format}"
    
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64_encoded
        }
    }


async def download_attachment(
    url: str, 
    config: Optional[Any] = None,
    mcp_tool_name: str = "download_attachment"
) -> str:
    """Download attachment from JIRA using authenticated API endpoint.
    
    Extracts attachment_id from URL and calls MCP tool to download via authenticated endpoint.
    Falls back to direct URL download if MCP tool is not available.
    
    Args:
        url: JIRA attachment URL (e.g., "https://domain.atlassian.net/rest/api/2/attachment/content/10036")
        config: Configuration object (optional, for MCP tool access)
        mcp_tool_name: MCP tool name for downloading attachment (default: issue-management-api endpoint)
        
    Returns:
        Path to the downloaded temporary file
        
    Raises:
        Exception: If download fails
    """
    import asyncio
    import base64
    import re
    
    # Extract attachment_id from URL
    # Pattern: .../attachment/content/{attachment_id} or .../attachment/{attachment_id}
    attachment_id_match = re.search(r'/attachment/(?:content/)?(\d+)', url)
    if not attachment_id_match:
        raise ValueError(f"Could not extract attachment_id from URL: {url}")
    
    attachment_id = attachment_id_match.group(1)
    
    # Try to use MCP tool if config is provided
    if config:
        try:
            from services.mcp_client import get_mcp_tools
            from agent.configuration import Configuration
            
            logger.info(f"download_attachment: Attempting to use MCP tool for attachment_id={attachment_id}")
            
            # Ensure config is a Configuration object
            if not isinstance(config, Configuration):
                raise ValueError(f"config must be a Configuration object, got {type(config)}")
            
            # Get MCP tools using the same pattern as _call_mcp_tool
            tools = await get_mcp_tools(config)
            
            # Find the tool by friendly name (from MCP_TOOL_NAME_MAPPING)
            tool = None
            for t in tools:
                if t.name == mcp_tool_name:
                    tool = t
                    logger.info(f"download_attachment: Found MCP tool: {t.name}")
                    break
            
            if not tool:
                available_tool_names = [t.name for t in tools]
                logger.warning(f"download_attachment: MCP tool '{mcp_tool_name}' not found. Available tools: {available_tool_names}")
                raise ValueError(f"MCP tool '{mcp_tool_name}' not found. Available tools: {available_tool_names}")
            
            # Invoke the tool
            logger.info(f"download_attachment: Invoking MCP tool with attachment_id={attachment_id}")
            result = await tool.ainvoke({"attachment_id": attachment_id})
            
            logger.debug(f"download_attachment: MCP tool result type: {type(result)}")
            
            # Parse result (should be dict with content_base64, filename, etc.)
            # Handle both dict and ToolMessage responses
            if isinstance(result, dict):
                if "content_base64" in result:
                    file_content_b64 = result["content_base64"]
                    filename = result.get("filename", "attachment")
                    file_extension = Path(filename).suffix or '.tmp'
                    
                    # Decode base64 content
                    file_content = base64.b64decode(file_content_b64)
                    
                    logger.info(f"download_attachment: Successfully downloaded via MCP tool: {filename} ({len(file_content)} bytes)")
                    
                    # Create temporary file and write content
                    def _create_and_write_temp_file():
                        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
                        temp_path = temp_file.name
                        temp_file.close()
                        with open(temp_path, 'wb') as f:
                            f.write(file_content)
                        return temp_path
                    
                    temp_path = await asyncio.to_thread(_create_and_write_temp_file)
                    return temp_path
                else:
                    logger.warning(f"download_attachment: MCP tool result missing 'content_base64' key. Keys: {list(result.keys())}")
                    raise ValueError(f"MCP tool result missing 'content_base64' key. Keys: {list(result.keys())}")
            else:
                # Try to extract from ToolMessage if that's what we got
                if hasattr(result, 'content'):
                    content = result.content
                    if isinstance(content, str):
                        try:
                            result_dict = json.loads(content)
                            if "content_base64" in result_dict:
                                file_content_b64 = result_dict["content_base64"]
                                filename = result_dict.get("filename", "attachment")
                                file_extension = Path(filename).suffix or '.tmp'
                                file_content = base64.b64decode(file_content_b64)
                                
                                logger.info(f"download_attachment: Successfully downloaded via MCP tool (from ToolMessage): {filename} ({len(file_content)} bytes)")
                                
                                def _create_and_write_temp_file():
                                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
                                    temp_path = temp_file.name
                                    temp_file.close()
                                    with open(temp_path, 'wb') as f:
                                        f.write(file_content)
                                    return temp_path
                                
                                temp_path = await asyncio.to_thread(_create_and_write_temp_file)
                                return temp_path
                        except (json.JSONDecodeError, KeyError) as e:
                            logger.warning(f"download_attachment: Could not parse ToolMessage content: {e}")
                            raise ValueError(f"Could not parse MCP tool response: {e}") from e
                
                raise ValueError(f"Unexpected MCP tool result type: {type(result)}")
        except Exception as e:
            logger.error(f"download_attachment: Error using MCP tool: {str(e)}")
            # Don't fall back to direct download if config is provided - raise the error
            raise Exception(f"Failed to download attachment via MCP tool: {str(e)}") from e
    
    # Fallback: Direct download from URL (may fail with 403 if not authenticated)
    parsed_url = urlparse(url)
    file_extension = Path(parsed_url.path).suffix or '.tmp'
    
    def _create_temp_file():
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
        temp_path = temp_file.name
        temp_file.close()
        return temp_path
    
    temp_path = await asyncio.to_thread(_create_temp_file)
    
    try:
        # Download the file asynchronously
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            # Write to temporary file in a separate thread to avoid blocking
            def _write_file():
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
            
            await asyncio.to_thread(_write_file)
            
        return temp_path
    except Exception as e:
        # Clean up on error in a separate thread
        def _cleanup():
            Path(temp_path).unlink(missing_ok=True)
        await asyncio.to_thread(_cleanup)
        raise Exception(f"Failed to download attachment from {url}: {str(e)}") from e


def extract_json_from_response(response_content: str) -> Dict[str, Any]:
    """Extract and parse JSON from LLM response.
    
    Handles cases where LLM wraps JSON in markdown code blocks or adds
    extra text before/after the JSON.
    
    Args:
        response_content: Raw response content from LLM
        
    Returns:
        Parsed JSON as dictionary
        
    Raises:
        ValueError: If no valid JSON can be extracted
        json.JSONDecodeError: If extracted string is not valid JSON
    """
    # First, try to clean the string
    cleaned = clean_json_string(response_content)
    
    # Try to parse directly
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # If that fails, try to find JSON object in the string
        # Look for {...} pattern
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # If still no luck, raise error
        raise ValueError(f"Could not extract valid JSON from response: {response_content[:200]}")


def extract_text_content(content) -> str:
    """Extract text content from LLM response which might be string or list.
    
    Args:
        content: Content from LLM response (can be string or list)
        
    Returns:
        Extracted text as string
    """
    if isinstance(content, list):
        # If content is a list, extract text from the first element
        if content and isinstance(content[0], dict) and "text" in content[0]:
            return content[0]["text"].strip()
        elif content and isinstance(content[0], str):
            return content[0].strip()
        else:
            return str(content).strip()
    else:
        return str(content).strip()
