"""Application settings and configuration management.

This module provides centralized configuration for the AICC Analyzer service,
loading settings from environment variables with sensible defaults.
"""

from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    """Application configuration settings."""

    # Application metadata
    app_name: str = Field(default="aicc-analyzer", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    environment: str = Field(default="dev", description="Environment: dev, stage, prod")
    context_path: str = Field(default="/analyzer", description="Root path for the API")
    
    # Server configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8080, description="Server port")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # AWS Services
    aws_region: str = Field(default="us-east-1", description="AWS region")
    analyzer_queue_url: str | None = Field(default=None, description="SQS analyzer queue URL")
    status_queue_url: str | None = Field(default=None, description="SQS status queue URL")
    audit_queue_url: str | None = Field(default=None, description="SQS audit queue URL")
    contract_documents_bucket: str | None = Field(default=None, description="S3 bucket for contract documents")
    execution_state_table: str | None = Field(default=None, description="DynamoDB execution state table")
    
    # Database configuration
    analyzer_db_host: str = Field(default="localhost", description="Analyzer database host")
    analyzer_db_port: int = Field(default=5432, description="Analyzer database port")
    analyzer_db_name: str = Field(default="analyzer_db_dev", description="Analyzer database name")
    analyzer_db_user: str = Field(default="analyzer_user", description="Analyzer database user")
    analyzer_db_password: str | None = Field(default=None, description="Analyzer database password")
    
    compliance_db_host: str = Field(default="localhost", description="Compliance database host")
    compliance_db_port: int = Field(default=5432, description="Compliance database port")
    compliance_db_name: str = Field(default="compliance_db_dev", description="Compliance database name")
    compliance_db_user: str = Field(default="compliance_user", description="Compliance database user")
    compliance_db_password: str | None = Field(default=None, description="Compliance database password")
    
    # Service configuration
    max_documents_per_job: int = Field(default=10, description="Maximum documents per analysis job")
    max_concurrent_analyses: int = Field(default=5, description="Maximum concurrent analyses")
    
    # Feature flags
    enable_textract: bool = Field(default=True, description="Enable Amazon Textract")
    enable_bedrock: bool = Field(default=True, description="Enable Amazon Bedrock LLM")
    enable_rule_caching: bool = Field(default=False, description="Enable rule result caching")
    enable_document_caching: bool = Field(default=False, description="Enable document caching")
    
    # External services
    contract_service_url: str | None = Field(default=None, description="Contract/Account service base URL")
    document_lake_url: str | None = Field(default=None, description="Document Lake/DMP base URL")
    prompt_management_url: str | None = Field(default=None, description="Prompt Management service URL")
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> AppSettings:
    """Get cached application settings.
    
    Returns:
        AppSettings: Application configuration loaded from environment.
    """
    return AppSettings()
