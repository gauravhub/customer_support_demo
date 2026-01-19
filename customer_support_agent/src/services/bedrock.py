"""Bedrock service for LLM interactions using Amazon Bedrock."""

import os

from langchain_aws import ChatBedrockConverse

from agent.configuration import Configuration


class BedrockService:
    """Service for interacting with Amazon Bedrock models.
    
    Provides methods to initialize LLMs (text, vision, with guardrails).
    
    AWS Credentials and Region:
    - Credentials are automatically picked up from boto3's credential chain:
      1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN)
      2. AWS credentials file (~/.aws/credentials)
      3. IAM role (if running on EC2/ECS/Lambda)
    - Region is explicitly set from AWS_REGION environment variable (defaults to us-west-2)
    """
    
    def __init__(self, config: Configuration):
        """Initialize Bedrock service with configuration.
        
        Args:
            config: Configuration object containing Bedrock settings
            
        Note:
            AWS credentials are automatically picked up by boto3 (used by ChatBedrockConverse)
            from environment variables, AWS credentials file, or IAM role.
            Region is read from AWS_REGION environment variable.
        """
        self.config = config
        # Region is explicitly passed to ChatBedrockConverse
        # Credentials are automatically picked up by boto3 from the credential chain
        self.aws_region = os.environ.get("AWS_REGION", "us-west-2")
        self.guardrail_id = config.guardrail_id
        self.guardrail_version = config.guardrail_version
    
    def get_reasoning_llm(self) -> ChatBedrockConverse:
        """Get reasoning LLM for agent tasks and complex reasoning with guardrails if configured.
        
        Uses Claude 4 Sonnet by default, which is optimized for reasoning tasks
        and agent workflows.
        Uses guardrails if guardrail_id is configured, otherwise returns plain LLM.
        For customer support, guardrails are recommended for content safety.
        
        Note:
            ChatBedrockConverse uses boto3, which automatically picks up AWS credentials
            from environment variables, AWS credentials file, or IAM role.
            Region is explicitly passed via region_name parameter.
        
        Returns:
            ChatBedrockConverse instance configured for reasoning/agent tasks
        """
        llm_params = {
            "model": self.config.reasoning_model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "region_name": self.aws_region,
        }
        
        # Add guardrails if configured
        if self.guardrail_id:
            llm_params["guardrails"] = {
                "guardrailIdentifier": self.guardrail_id,
                "guardrailVersion": self.guardrail_version,
                "trace": "enabled"
            }
        
        return ChatBedrockConverse(**llm_params)
