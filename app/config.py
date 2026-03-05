from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Anthropic
    anthropic_api_key: str

    # AWS
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # Pinpoint
    pinpoint_app_id: str = ""
    pinpoint_origination_number: str = ""

    # Default route
    default_route_type: Literal["webhook", "sms"] = "webhook"
    default_route_url: str = ""   # used when type=webhook
    default_route_to: str = ""    # used when type=sms

    # Server
    base_url: str = "http://localhost:8000"

    # Storage
    rules_file: str = "data/rules.json"
    endpoints_file: str = "data/endpoints.json"
    threads_file: str = "data/threads.json"


settings = Settings()
