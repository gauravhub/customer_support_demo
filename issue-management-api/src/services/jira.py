"""JIRA service wrapper for issue management API.

This service wraps the JIRA Python package to provide a simplified interface
for interacting with JIRA issues. It's designed to be used by the FastAPI
endpoints in the issue-management-api.
"""

from typing import Optional, Any, Dict
from jira import JIRA
from jira.resources import Issue

from src.config import Configuration


class JiraService:
    """Service for interacting with JIRA issues.
    
    Provides methods to:
    - Fetch issue information
    - Get field values from issues
    - Update issue fields
    - Get attachments
    """
    
    def __init__(self, config: Configuration):
        """Initialize JIRA service with configuration.
        
        Args:
            config: Configuration object containing JIRA settings
        """
        self.config = config
    
    def _get_client(self) -> JIRA:
        """Create and return a JIRA client object.
        
        Returns:
            JIRA client instance configured with credentials
            
        Raises:
            ValueError: If required credentials are not configured
        """
        if not self.config.jira_api_username or not self.config.jira_api_token or not self.config.jira_instance_url:
            raise ValueError(
                "JIRA credentials not configured. "
                "Set JIRA_API_USERNAME, JIRA_API_TOKEN, and JIRA_INSTANCE_URL environment variables."
            )
        
        options = {'server': self.config.jira_instance_url}
        jira = JIRA(options, basic_auth=(self.config.jira_api_username, self.config.jira_api_token))
        return jira
    
    def fetch_issue(self, issue_key: str) -> Optional[Issue]:
        """Fetch a JIRA issue by key.
        
        Args:
            issue_key: JIRA issue key (e.g., "AS-5", "PROJ-123")
            
        Returns:
            JIRA Issue object if found, None otherwise
        """
        if not issue_key:
            return None
        
        try:
            jira = self._get_client()
            issue = jira.issue(issue_key)
            return issue
        except Exception as e:
            print(f"Error fetching issue {issue_key}: {str(e)}")
            return None
    
    def get_issue_dict(self, issue_key: str) -> Optional[Dict[str, Any]]:
        """Get issue information as a dictionary.
        
        Args:
            issue_key: JIRA issue key (e.g., "AS-5")
            
        Returns:
            Dictionary with issue information, or None if not found
        """
        issue = self.fetch_issue(issue_key)
        if not issue:
            return None
        
        # Convert issue to dictionary
        issue_dict = {
            "key": issue.key,
            "summary": issue.fields.summary,
            "description": issue.fields.description,
            "status": issue.fields.status.name if issue.fields.status else None,
            "assignee": issue.fields.assignee.emailAddress if issue.fields.assignee else None,
            "reporter": issue.fields.reporter.emailAddress if issue.fields.reporter else None,
            "created": issue.fields.created,
            "updated": issue.fields.updated,
            "issue_type": issue.fields.issuetype.name if issue.fields.issuetype else None,
            "priority": issue.fields.priority.name if issue.fields.priority else None,
            "project": issue.fields.project.key if issue.fields.project else None,
        }
        
        return issue_dict
    
    def get_attachments(self, issue_key: str) -> list[Dict[str, Any]]:
        """Get attachments for a JIRA issue.
        
        Args:
            issue_key: JIRA issue key (e.g., "AS-5")
            
        Returns:
            List of attachment dictionaries with id, filename, size, mimeType, content URL, etc.
        """
        try:
            jira = self._get_client()
            issue = jira.issue(issue_key)
            
            attachments = []
            # Access attachments from issue.fields.attachment
            # The JIRA package provides Attachment objects that need to be serialized
            if hasattr(issue.fields, 'attachment') and issue.fields.attachment:
                for attachment in issue.fields.attachment:
                    # Get attachment attributes safely (JIRA package Attachment object attributes may vary)
                    attachment_id = getattr(attachment, 'id', None)
                    attachment_filename = getattr(attachment, 'filename', getattr(attachment, 'name', 'attachment'))
                    attachment_size = getattr(attachment, 'size', None)
                    attachment_mimeType = getattr(attachment, 'mimeType', getattr(attachment, 'mimeType', None))
                    attachment_content = getattr(attachment, 'content', getattr(attachment, 'self', None))
                    attachment_thumbnail = getattr(attachment, 'thumbnail', None)
                    attachment_created = getattr(attachment, 'created', None)
                    
                    # Get author information safely
                    attachment_author = None
                    if hasattr(attachment, 'author') and attachment.author:
                        attachment_author = getattr(attachment.author, 'emailAddress', 
                                                   getattr(attachment.author, 'displayName', 
                                                          getattr(attachment.author, 'name', None)))
                    
                    attachment_dict = {
                        "id": attachment_id,
                        "filename": attachment_filename,
                        "size": attachment_size,
                        "mimeType": attachment_mimeType,
                        "content": attachment_content,  # URL to download the attachment
                        "thumbnail": attachment_thumbnail,
                        "created": attachment_created,
                        "author": attachment_author,
                    }
                    attachments.append(attachment_dict)
            
            return attachments
        except Exception as e:
            print(f"Error retrieving attachments for {issue_key}: {str(e)}")
            return []
    
    def get_field_value(self, issue_key: str, field_name: str) -> Optional[Any]:
        """Retrieve the current value of a field from a JIRA issue.
        
        Args:
            issue_key: JIRA issue key (e.g., "AS-5")
            field_name: Field name (e.g., "reporter", "customfield_10071")
            
        Returns:
            Field value if found, None otherwise
        """
        try:
            jira = self._get_client()
            issue = jira.issue(issue_key)
            
            # Access field value through issue.fields
            field_value = getattr(issue.fields, field_name, None)
            
            # Handle special cases for user objects
            if field_value and hasattr(field_value, 'emailAddress'):
                return field_value.emailAddress
            
            return field_value
        except Exception as e:
            print(f"Error retrieving field value for {issue_key}: {str(e)}")
            return None
    
    def update_field(self, issue_key: str, field_name: str, value: Any) -> bool:
        """Update a field value in a JIRA issue.
        
        Args:
            issue_key: JIRA issue key (e.g., "AS-5")
            field_name: Field name (e.g., "customfield_10071")
            value: Value to set
            
        Returns:
            True if successful, False otherwise
        """
        try:
            jira = self._get_client()
            issue = jira.issue(issue_key)
            issue.update(fields={field_name: value})
            return True
        except Exception as e:
            print(f"Error updating field {field_name} for issue {issue_key}: {str(e)}")
            return False
    