"""Configuration class for JIRA settings."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if it exists
# In Docker container: /app/src/config.py -> /app/.env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


class Configuration:
    """Configuration class for JIRA API settings."""
    
    def __init__(
        self,
        jira_api_username: str = None,
        jira_api_token: str = None,
        jira_instance_url: str = None,
        jira_project_key: str = None,
        jira_assignee_username: str = None,
        jira_category_field_id: str = None,
        jira_response_field_id: str = None,
    ):
        """Initialize configuration with JIRA settings.
        
        Args:
            jira_api_username: JIRA API username/email
            jira_api_token: JIRA API token
            jira_instance_url: JIRA instance URL (e.g., https://your-domain.atlassian.net)
            jira_project_key: JIRA project key (e.g., "AS")
            jira_assignee_username: Default assignee username
            jira_category_field_id: Custom field ID for category (without 'customfield_' prefix)
            jira_response_field_id: Custom field ID for response (without 'customfield_' prefix)
        """
        self._jira_api_username = jira_api_username or os.getenv("JIRA_API_USERNAME", "")
        self._jira_api_token = jira_api_token or os.getenv("JIRA_API_TOKEN", "")
        self._jira_instance_url = jira_instance_url or os.getenv("JIRA_INSTANCE_URL", "")
        self._jira_project_key = jira_project_key or os.getenv("JIRA_PROJECT_KEY", "")
        self._jira_assignee_username = jira_assignee_username or os.getenv("JIRA_ASSIGNEE_USERNAME", "")
        self._jira_category_field_id = jira_category_field_id or os.getenv("JIRA_CATEGORY_FIELD_ID", "")
        self._jira_response_field_id = jira_response_field_id or os.getenv("JIRA_RESPONSE_FIELD_ID", "")
    
    @property
    def jira_api_username(self) -> str:
        """Get the JIRA API username."""
        return self._jira_api_username
    
    @property
    def jira_api_token(self) -> str:
        """Get the JIRA API token."""
        return self._jira_api_token
    
    @property
    def jira_instance_url(self) -> str:
        """Get the JIRA instance URL."""
        return self._jira_instance_url
    
    @property
    def jira_project_key(self) -> str:
        """Get the JIRA project key."""
        return self._jira_project_key
    
    @property
    def jira_assignee_username(self) -> str:
        """Get the default assignee username."""
        return self._jira_assignee_username
    
    @property
    def jira_category_field_id(self) -> str:
        """Get the category field ID."""
        return self._jira_category_field_id
    
    @property
    def jira_response_field_id(self) -> str:
        """Get the response field ID."""
        return self._jira_response_field_id
