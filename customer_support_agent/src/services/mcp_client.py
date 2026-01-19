"""MCP Client Service using langchain-mcp-adapters.

This module provides a function to get MCP tools using MultiServerMCPClient
with automatic token refresh via OAuthTokenAuth.
"""

import base64
import json
import time
import urllib.parse
import urllib.request
from typing import List, Any

import httpx
from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from agent.configuration import Configuration


# Mapping from friendly tool names to MCP Gateway tool names
# This provides clean, readable names for tools instead of the long API-prefixed names
MCP_TOOL_NAME_MAPPING = {
    # Order Management API tools
    "find_customer": "order-management-api___find_customer_api_customer_get",
    "find_order": "order-management-api___find_order_api_order_get",
    "find_transaction": "order-management-api___find_transaction_api_transaction_get",
    "get_transaction_for_order": "order-management-api___get_transaction_for_order_api_transaction_order__order_no__get",
    "get_refund_for_order": "order-management-api___get_refund_for_order_api_refund_order__order_no__get",
    
    # Issue Management API tools
    "get_issue": "issue-management-api___get_issue_api_issue__issue_key__get",
    "get_issue_attachments": "issue-management-api___get_issue_attachments_api_issue__issue_key__attachments_get",
    "get_issue_field": "issue-management-api___get_issue_field_api_issue__issue_key__field_get",
    "update_issue_field": "issue-management-api___update_issue_field_api_issue__issue_key__field_put",
    
    # Product Knowledge Base tools
    "query_products_kb": "product-knowledge-base___Retrieve",
}


class OAuthTokenAuth(httpx.Auth):
    """OAuth2 authentication for MCP Gateway using Cognito client credentials flow.
    
    Implements httpx.Auth interface to automatically inject and refresh tokens
    on each HTTP request. Tokens are refreshed when they expire (24 hours).
    
    Example:
        >>> from agent.configuration import Configuration
        >>> from services.mcp_client import OAuthTokenAuth
        >>> 
        >>> config = Configuration.from_environment()
        >>> auth = OAuthTokenAuth(config)
        >>> 
        >>> # Use with MultiServerMCPClient
        >>> client = MultiServerMCPClient({
        ...     "mcp-gateway": {
        ...         "transport": "http",
        ...         "url": config.mcp_server_url,
        ...         "auth": auth  # Pass auth object instead of static headers
        ...     }
        ... })
    """
    
    def __init__(self, config: Configuration):
        """Initialize OAuth authentication with configuration.
        
        Args:
            config: Configuration object containing Cognito credentials
            
        Raises:
            RuntimeError: If required Cognito credentials are missing
        """
        if not all([
            config.mcp_cognito_client_id,
            config.mcp_cognito_client_secret,
            config.mcp_cognito_token_endpoint
        ]):
            raise RuntimeError(
                "MCP Cognito credentials not configured. "
                "Set MCP_COGNITO_CLIENT_ID, MCP_COGNITO_CLIENT_SECRET, "
                "and MCP_COGNITO_TOKEN_ENDPOINT environment variables."
            )
        
        self.config = config
        self._token: str | None = None
        self._expires_at: float = 0.0
        
    def _refresh_token(self) -> None:
        """Get a fresh access token from Cognito.
        
        Uses client credentials flow with the credentials from configuration.
        Token is cached until it expires (typically 24 hours).
        
        Raises:
            RuntimeError: If token acquisition fails
        """
        if not self.config.mcp_cognito_token_endpoint:
            raise RuntimeError(
                "MCP_COGNITO_TOKEN_ENDPOINT is not configured. "
                "Set the environment variable with the Cognito token endpoint URL."
            )
        
        # Validate URL format
        endpoint = self.config.mcp_cognito_token_endpoint
        if not endpoint.startswith(('http://', 'https://')):
            raise RuntimeError(
                f"Invalid MCP_COGNITO_TOKEN_ENDPOINT format: {endpoint}\n"
                f"Expected format: https://<cognito-domain>.auth.<region>.amazoncognito.com/oauth2/token"
            )
        
        # Full scope format: {resource_server_identifier}/gateway.access
        scope = f'{self.config.mcp_resource_server_id}/gateway.access'
        
        # Use basic auth
        auth_string = f"{self.config.mcp_cognito_client_id}:{self.config.mcp_cognito_client_secret}"
        auth_bytes = auth_string.encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
        
        data = urllib.parse.urlencode({
            'grant_type': 'client_credentials',
            'scope': scope
        }).encode('utf-8')
        
        req = urllib.request.Request(
            self.config.mcp_cognito_token_endpoint,
            data=data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': f'Basic {auth_b64}'
            }
        )
        
        try:
            # Add timeout to prevent hanging (10 seconds)
            with urllib.request.urlopen(req, timeout=10) as response:
                token_data = json.loads(response.read().decode('utf-8'))
                access_token = token_data.get('access_token')
                
                if not access_token:
                    raise RuntimeError("No access token in response")
                
                # Cache token and expiration
                self._token = access_token
                expires_in = token_data.get('expires_in', 86400)  # Default 24 hours
                # Refresh 1 minute before expiry
                self._expires_at = time.time() + expires_in - 60
                
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            raise RuntimeError(
                f"Failed to get access token from {self.config.mcp_cognito_token_endpoint} "
                f"(HTTP {e.code}): {error_body}"
            )
        except urllib.error.URLError as e:
            error_msg = str(e)
            if "Name or service not known" in error_msg or "[Errno -2]" in error_msg:
                raise RuntimeError(
                    f"DNS lookup failed for Cognito token endpoint: {self.config.mcp_cognito_token_endpoint}\n"
                    f"This usually means:\n"
                    f"  1. The Cognito domain does not exist or is incorrect\n"
                    f"  2. Network connectivity issues\n"
                    f"  3. DNS resolution problems\n"
                    f"Please verify MCP_COGNITO_TOKEN_ENDPOINT is set to a valid Cognito domain.\n"
                    f"Expected format: https://<cognito-domain>.auth.<region>.amazoncognito.com/oauth2/token"
                ) from e
            else:
                raise RuntimeError(
                    f"Network error connecting to {self.config.mcp_cognito_token_endpoint}: {error_msg}"
                ) from e
        except Exception as e:
            raise RuntimeError(
                f"Failed to get access token from {self.config.mcp_cognito_token_endpoint}: {str(e)}"
            ) from e
    
    def auth_flow(self, request: httpx.Request) -> httpx.Request:
        """httpx.Auth interface: inject Authorization header with fresh token.
        
        This method is called by httpx on every request. It ensures a valid
        token is available and injects it into the request headers.
        
        Args:
            request: HTTP request to authenticate
            
        Returns:
            Request with Authorization header added
            
        Yields:
            Authenticated request
        """
        # Refresh token if needed (expired or not yet obtained)
        if self._token is None or time.time() >= self._expires_at:
            self._refresh_token()
        
        # Inject Authorization header
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


async def get_mcp_tools(config: Configuration) -> List[BaseTool]:
    """Get LangChain tools from MCP Gateway with automatic token refresh.
    
    Creates a MultiServerMCPClient with OAuthTokenAuth for automatic token
    refresh. Tokens are refreshed automatically when they expire.
    
    Tool names are mapped to friendly names (e.g., "find_customer" instead of
    "order-management-api___find_customer_api_customer_get") using explicit mappings.
    Tools that don't have a mapping keep their original name. The original tool name
    is preserved in metadata for internal use.
    
    Args:
        config: Configuration object containing MCP Gateway settings
        
    Returns:
        List of LangChain BaseTool instances from the MCP Gateway with friendly names
        
    Raises:
        RuntimeError: If tool retrieval fails or configuration is invalid
    """
    if not config.mcp_server_url:
        raise RuntimeError(
            "MCP server URL not configured. Set MCP_SERVER_URL environment variable."
        )
    
    # Create OAuth auth object for automatic token refresh
    auth = OAuthTokenAuth(config)
    
    # Create client configuration with HTTP transport and auth object
    client_config = {
        "mcp-gateway": {
            "transport": "http",
            "url": config.mcp_server_url,
            "auth": auth  # Pass auth object instead of static headers
        }
    }
    
    # Create MultiServerMCPClient
    client = MultiServerMCPClient(client_config)
    
    # Get tools from MCP Gateway
    try:
        tools = await client.get_tools()
        
        # Get Knowledge Base ID from configuration
        # This is needed to auto-inject into the Retrieve tool
        kb_id = config.product_kb_id
        
        # Map tool names to friendly names
        # The MCP adapter tools store the original tool name internally for invocation,
        # so we can safely change the display name without breaking functionality
        mapped_tools = []
        reverse_mapping = {v: k for k, v in MCP_TOOL_NAME_MAPPING.items()}
        
        for tool in tools:
            original_name = tool.name
            
            # Use mapped friendly name if available, otherwise keep original name
            final_name = reverse_mapping.get(original_name, original_name)
            
            # Note: We no longer wrap the tool here. Instead, we use middleware
            # (KnowledgeBaseIDMiddleware) to inject knowledgeBaseId at runtime.
            # This is cleaner and avoids Pydantic model restrictions.
            
            # Directly modify the name attribute (tools are mutable)
            tool.name = final_name
            
            # Store original name in metadata for debugging and internal reference
            if hasattr(tool, 'metadata'):
                if tool.metadata:
                    tool.metadata["_original_name"] = original_name
                else:
                    tool.metadata = {"_original_name": original_name}
            
            mapped_tools.append(tool)
        
        return mapped_tools
    except Exception as e:
        raise RuntimeError(f"Failed to get tools from MCP Gateway: {str(e)}") from e
