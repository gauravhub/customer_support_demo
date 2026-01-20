"""FastAPI REST API for JIRA issue management."""

import json
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status, Body, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.config import Configuration
from src.services.jira import JiraService

# Initialize configuration and JIRA service
config = Configuration()
jira_service = JiraService(config)

# Load API keys from file
def load_api_keys() -> set:
    """Load base64-encoded API keys from JSON file.
    
    Returns:
        Set of valid API keys (base64-encoded strings)
    """
    project_root = Path(__file__).parent.parent.parent
    api_keys_file = project_root / "data" / "api_keys.json"
    
    try:
        with open(api_keys_file, 'r') as f:
            data = json.load(f)
            # Create a set of API keys for quick lookup
            if isinstance(data, list):
                return set(data)
            return set()
    except FileNotFoundError:
        print(f"WARNING: API keys file not found at {api_keys_file}")
        return set()
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse API keys file: {e}")
        return set()


# Cache API keys in memory
_api_keys_cache: Optional[set] = None

def get_api_keys() -> set:
    """Get API keys (cached)."""
    global _api_keys_cache
    if _api_keys_cache is None:
        _api_keys_cache = load_api_keys()
    return _api_keys_cache


def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Verify API key from X-API-Key header.
    
    Checks if the provided API key (base64-encoded) matches any key in the allowed list.
    
    Args:
        x_api_key: API key from X-API-Key header (base64-encoded)
    
    Returns:
        The API key if valid
    
    Raises:
        HTTPException: If API key is invalid or missing
    """
    api_keys = get_api_keys()
    
    if not x_api_key or x_api_key not in api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    
    return x_api_key


app = FastAPI(
    title="Issue Management API",
    description="REST API for managing JIRA issues (X-API-Key header required)",
    version="0.1.0"
)


@app.on_event("startup")
async def startup_event():
    """Load API keys on application startup."""
    try:
        # Load API keys
        api_keys = get_api_keys()
        print(f"Loaded {len(api_keys)} active API key(s)")
        
        # Verify JIRA configuration
        if not config.jira_api_username or not config.jira_api_token or not config.jira_instance_url:
            print("WARNING: JIRA credentials not fully configured. Some endpoints may not work.")
        else:
            print("JIRA configuration loaded successfully")
    except Exception as e:
        print(f"ERROR: Failed to initialize: {str(e)}")


@app.get("/api/issue/{issue_key}")
async def get_issue(
    issue_key: str,
    _api_key: str = Depends(verify_api_key)  # Verified but not used in function
) -> dict:
    """Get issue information by issue key.
    
    Args:
        issue_key: JIRA issue key (e.g., "AS-5", "PROJ-123")
    
    Returns:
        Dictionary with issue information if found, empty dict if not found.
        Contains: key, summary, description, status, assignee, reporter, etc.
    """
    if not issue_key:
        return {}
    
    try:
        issue = jira_service.get_issue_dict(issue_key)
        if issue:
            return issue
        return {}
    except Exception as e:
        return {"error": f"Could not fetch issue: {str(e)}"}


@app.get("/api/issue/{issue_key}/field")
async def get_issue_field(
    issue_key: str,
    field_name: str = Query(..., description="Field name (e.g., 'reporter', 'customfield_10071')"),
    _api_key: str = Depends(verify_api_key)  # Verified but not used in function
) -> dict:
    """Get a specific field value from an issue.
    
    Args:
        issue_key: JIRA issue key (e.g., "AS-5")
        field_name: Field name to retrieve (e.g., "reporter", "customfield_10071")
    
    Returns:
        Dictionary with field value if found, empty dict if not found.
    """
    if not issue_key or not field_name:
        return {}
    
    try:
        value = jira_service.get_field_value(issue_key, field_name)
        if value is not None:
            return {field_name: value}
        return {}
    except Exception as e:
        return {"error": f"Could not get field value: {str(e)}"}


@app.get("/api/issue/{issue_key}/attachments")
async def get_issue_attachments(
    issue_key: str,
    _api_key: str = Depends(verify_api_key)  # Verified but not used in function
) -> dict:
    """Get attachments for an issue.
    
    Args:
        issue_key: JIRA issue key (e.g., "AS-5")
    
    Returns:
        Dictionary with list of attachments, each containing id, filename, size, mimeType, content URL, etc.
    """
    if not issue_key:
        return {"error": "issue_key is required"}
    
    try:
        attachments = jira_service.get_attachments(issue_key)
        return {"attachments": attachments, "count": len(attachments)}
    except Exception as e:
        return {"error": f"Could not fetch attachments: {str(e)}"}


class UpdateFieldRequest(BaseModel):
    """Request model for updating an issue field."""
    field_name: str
    value: str


@app.put("/api/issue/{issue_key}/field")
async def update_issue_field(
    issue_key: str,
    request: UpdateFieldRequest = Body(...),
    _api_key: str = Depends(verify_api_key)  # Verified but not used in function
) -> dict:
    """Update a field value in an issue.
    
    Args:
        issue_key: JIRA issue key (e.g., "AS-5")
        request: Request body with field_name and value
    
    Returns:
        Dictionary with success status
    
    Note:
        To assign an issue, use field_name="assignee" with the assignee email/username as value.
    """
    if not issue_key or not request.field_name:
        return {"error": "issue_key and field_name are required"}
    
    try:
        success = jira_service.update_field(issue_key, request.field_name, request.value)
        if success:
            return {"status": "success", "message": f"Field {request.field_name} updated successfully"}
        return {"error": "Failed to update field"}
    except Exception as e:
        return {"error": f"Could not update field: {str(e)}"}


@app.get("/api/attachment/{attachment_id}")
async def download_attachment(
    attachment_id: str,
    _api_key: str = Depends(verify_api_key)  # Verified but not used in function
) -> dict:
    """Download an attachment from JIRA.
    
    Uses authenticated JIRA session to download the attachment file.
    Returns base64-encoded content for MCP compatibility.
    
    Args:
        attachment_id: JIRA attachment ID (e.g., "10036")
    
    Returns:
        Dictionary with base64-encoded file content, filename, and content_type
    
    Raises:
        HTTPException: If attachment not found or download fails
    """
    import base64
    
    if not attachment_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="attachment_id is required"
        )
    
    try:
        file_content, filename, content_type = jira_service.download_attachment(attachment_id)
        
        # Encode file content as base64 for JSON response (MCP compatibility)
        file_content_b64 = base64.b64encode(file_content).decode('utf-8')
        
        return {
            "attachment_id": attachment_id,
            "filename": filename,
            "content_type": content_type,
            "content_base64": file_content_b64,
            "size": len(file_content)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not download attachment: {str(e)}"
        )


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Issue Management API",
        "version": "0.1.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
