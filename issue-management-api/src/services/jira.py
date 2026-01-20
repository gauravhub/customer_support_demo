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
        
        # Add custom fields: Category and Response
        if self.config.jira_category_field_id:
            category_field_name = f"customfield_{self.config.jira_category_field_id}"
            category_value = getattr(issue.fields, category_field_name, None)
            # Handle case where custom field might be an object with a 'value' attribute
            if category_value and hasattr(category_value, 'value'):
                issue_dict["category"] = category_value.value
            elif category_value:
                issue_dict["category"] = category_value
        
        if self.config.jira_response_field_id:
            response_field_name = f"customfield_{self.config.jira_response_field_id}"
            response_value = getattr(issue.fields, response_field_name, None)
            # Response field is typically a string, but handle object case too
            if response_value and hasattr(response_value, 'value'):
                issue_dict["response"] = response_value.value
            elif response_value:
                issue_dict["response"] = response_value
        
        # Add attachments array (list of download URLs as strings)
        attachments = []
        if hasattr(issue.fields, 'attachment') and issue.fields.attachment:
            for attachment in issue.fields.attachment:
                # Get download URL (content field)
                attachment_content = getattr(attachment, 'content', getattr(attachment, 'self', None))
                if attachment_content:
                    attachments.append(attachment_content)
        
        issue_dict["attachments"] = attachments
        
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
            field_name: Field name (e.g., "customfield_10071", "assignee", "response", or "category")
            value: Value to set
            
        Returns:
            True if successful, False otherwise
        """
        try:
            jira = self._get_client()
            issue = jira.issue(issue_key)
            
            # Special handling for assignee field
            # Use JIRA's assign_issue method which handles user lookup automatically
            if field_name == "assignee":
                try:
                    # Use JIRA's built-in assign_issue method which handles user lookup
                    # This method accepts username, email, or accountId and handles conversion
                    jira.assign_issue(issue_key, value)
                    print(f"Successfully updated assignee field for issue {issue_key} to {value}")
                except Exception as assign_error:
                    # If assign_issue fails, try manual assignment as fallback
                    print(f"Warning: assign_issue failed, trying manual assignment: {str(assign_error)}")
                    try:
                        # Try to find user by email/username
                        user = jira.user(value)
                        # Use accountId if available (for JIRA Cloud), otherwise use emailAddress
                        if hasattr(user, 'accountId') and user.accountId:
                            assignee_value = {"accountId": user.accountId}
                        elif hasattr(user, 'emailAddress') and user.emailAddress:
                            assignee_value = {"emailAddress": user.emailAddress}
                        else:
                            # Fallback: try using the value directly as accountId
                            assignee_value = {"accountId": value}
                        
                        issue.update(fields={"assignee": assignee_value})
                        print(f"Successfully updated assignee field for issue {issue_key} to {value} (via manual assignment)")
                    except Exception as manual_error:
                        error_msg = f"Error assigning issue {issue_key} to {value}: {str(manual_error)}"
                        print(f"ERROR: {error_msg}")
                        raise Exception(error_msg) from manual_error
            
            # Special handling for response custom field
            # If field_name is "response", convert to custom field ID
            elif field_name == "response":
                if not self.config.jira_response_field_id:
                    print(f"ERROR: jira_response_field_id not configured, cannot update response field")
                    return False
                
                response_field_name = f"customfield_{self.config.jira_response_field_id}"
                # Custom fields can be updated directly with the value
                # For text fields, value is a string
                issue.update(fields={response_field_name: value})
                print(f"Successfully updated response field (customfield_{self.config.jira_response_field_id}) for issue {issue_key}")
            
            # Special handling for category custom field
            # If field_name is "category", convert to custom field ID
            elif field_name == "category":
                if not self.config.jira_category_field_id:
                    print(f"ERROR: jira_category_field_id not configured, cannot update category field")
                    return False
                
                category_field_name = f"customfield_{self.config.jira_category_field_id}"
                # Custom fields can be updated directly with the value
                # For text fields, value is a string
                issue.update(fields={category_field_name: value})
                print(f"Successfully updated category field (customfield_{self.config.jira_category_field_id}) for issue {issue_key}")
            
            else:
                # For other fields (including custom fields), use value directly
                issue.update(fields={field_name: value})
                print(f"Successfully updated field {field_name} for issue {issue_key}")
            
            return True
        except Exception as e:
            print(f"ERROR: Error updating field {field_name} for issue {issue_key}: {str(e)}")
            import traceback
            print(f"ERROR: Traceback:\n{traceback.format_exc()}")
            return False
    
    def download_attachment(self, attachment_id: str) -> tuple[bytes, str, str]:
        """Download an attachment from JIRA using authenticated session.
        
        Uses the JIRA package's session for authentication to download the attachment.
        
        Args:
            attachment_id: JIRA attachment ID (e.g., "10036")
            
        Returns:
            Tuple of (file_content: bytes, filename: str, content_type: str)
            
        Raises:
            Exception: If download fails or attachment not found
        """
        try:
            jira = self._get_client()
            
            # Get attachment object
            attachment = jira.attachment(attachment_id)
            
            # Get attachment attributes
            attachment_url = getattr(attachment, 'content', getattr(attachment, 'self', None))
            attachment_filename = getattr(attachment, 'filename', getattr(attachment, 'name', 'attachment'))
            attachment_mimeType = getattr(attachment, 'mimeType', 'application/octet-stream')
            
            if not attachment_url:
                raise ValueError("Could not find attachment URL in attachment object")
            
            # Use the JIRA client's session to download the attachment
            # This ensures proper authentication and handles API versioning
            response = jira._session.get(attachment_url, stream=True)
            response.raise_for_status()
            
            # Read the file content
            file_content = b""
            for chunk in response.iter_content(chunk_size=1024):
                file_content += chunk
            
            return (file_content, attachment_filename, attachment_mimeType)
        except Exception as e:
            error_msg = f"Error downloading attachment {attachment_id}: {str(e)}"
            print(f"ERROR: {error_msg}")
            raise Exception(error_msg) from e
    