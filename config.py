"""
Unified configuration management for translate_agent.

Centralizes all configuration, magic numbers, thresholds, and environment variables
in a single, type-safe location. Supports multiple environments (dev, test, prod).
"""

import os
from dataclasses import dataclass, field
from typing import List, Set, Optional


@dataclass
class Config:
    """Application configuration with environment variable overrides."""

    # ============================================================================
    # LLM Configuration
    # ============================================================================
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", ""))
    
    small_model_name: str = field(default_factory=lambda: os.getenv("SMALL_MODEL_NAME", "gpt-4.1-mini"))
    large_model_name: str = field(default_factory=lambda: os.getenv("LARGE_MODEL_NAME", "gpt-4o"))
    
    small_model_fallbacks: List[str] = field(default_factory=lambda: [
        m.strip()
        for m in os.getenv("SMALL_MODEL_FALLBACKS", "gpt-4o").split(",")
        if m.strip()
    ])
    disabled_model_names: Set[str] = field(default_factory=lambda: {
        m.strip()
        for m in os.getenv("DISABLED_MODEL_NAMES", "").split(",")
        if m.strip()
    })

    # ============================================================================
    # Quality Check Thresholds (Content Quality)
    # ============================================================================
    unchanged_ratio_threshold: float = 0.10  # 10% 未翻译段落触发告警
    en_cjk_ratio_threshold: float = 0.08     # 8% CJK 残留触发告警
    source_residual_ratio_threshold: float = 0.08  # 8% 源语言残留触发告警
    jp_latin_ratio_threshold: float = 0.08   # 8% 拉丁字母残留触发告警

    # ============================================================================
    # Quality Check Thresholds (PPT Quality)
    # ============================================================================
    ppt_unchanged_ratio_threshold: float = 0.10  # PPT 未翻译比例
    ppt_source_residual_ratio_threshold: float = 0.08  # PPT 源语言残留比例

    # ============================================================================
    # Flask / Web Service Configuration
    # ============================================================================
    flask_host: str = os.getenv("FLASK_HOST", "0.0.0.0")
    flask_port: int = int(os.getenv("FLASK_PORT", "5000"))
    flask_debug: bool = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    
    max_workers: int = int(os.getenv("TRANSLATE_AGENT_WORKERS", "3"))
    max_upload_size_mb: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "100"))
    
    # ============================================================================
    # Task Management Configuration
    # ============================================================================
    task_retention_seconds: int = max(300, int(os.getenv("TRANSLATE_AGENT_TASK_RETENTION_SECONDS", "21600")))
    task_cleanup_interval_seconds: int = max(30, int(os.getenv("TRANSLATE_AGENT_TASK_CLEANUP_INTERVAL_SECONDS", "300")))
    max_task_cache_size: int = int(os.getenv("MAX_TASK_CACHE_SIZE", "10000"))
    
    # ============================================================================
    # File & Storage Configuration
    # ============================================================================
    upload_folder: str = os.getenv("UPLOAD_FOLDER", "./uploads")
    temp_folder: str = os.getenv("TEMP_FOLDER", "./temp")

    # ============================================================================
    # Logging Configuration
    # ============================================================================
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir: str = os.getenv("LOG_DIR", "./logs")
    log_max_bytes: int = int(os.getenv("LOG_MAX_BYTES", "10485760"))  # 10MB
    log_backup_count: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))

    # ============================================================================
    # Security Configuration
    # ============================================================================
    auth_token: str = os.getenv("TRANSLATE_AGENT_TOKEN", "")
    require_auth: bool = os.getenv("REQUIRE_AUTH", "False").lower() == "true"

    # ============================================================================
    # LLM Call Configuration
    # ============================================================================
    llm_call_timeout_seconds: int = int(os.getenv("LLM_CALL_TIMEOUT", "30"))
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "3"))
    llm_temperature: float = 0.2  # 偏向确定性翻译

    # ============================================================================
    # Translation Configuration
    # ============================================================================
    glossary_sample_size: int = 100  # 用于生成词汇表的源文本样本量
    glossary_extraction_terms: int = 15  # 从样本中提取多少个关键术语

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Ensure directories exist
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.upload_folder, exist_ok=True)
        os.makedirs(self.temp_folder, exist_ok=True)


# Global config instance
config = Config()


def get_config() -> Config:
    """Get the global config instance."""
    return config


def validate_config() -> bool:
    """Validate critical configuration."""
    errors = []
    
    if not config.openai_api_key:
        errors.append("OPENAI_API_KEY is not configured")
    
    if not config.small_model_name:
        errors.append("SMALL_MODEL_NAME is not configured")
    
    if not config.large_model_name:
        errors.append("LARGE_MODEL_NAME is not configured")
    
    if config.max_workers < 1:
        errors.append(f"TRANSLATE_AGENT_WORKERS must be >= 1, got {config.max_workers}")
    
    if config.task_retention_seconds < 300:
        errors.append(f"TRANSLATE_AGENT_TASK_RETENTION_SECONDS must be >= 300, got {config.task_retention_seconds}")
    
    if errors:
        for error in errors:
            print(f"❌ Configuration Error: {error}")
        return False
    
    return True


if __name__ == "__main__":
    # Print current configuration for debugging
    print("📋 Current Configuration:")
    print(f"  LLM: {config.small_model_name} (fallback: {config.small_model_fallbacks})")
    print(f"  Large Model: {config.large_model_name}")
    print(f"  Flask: {config.flask_host}:{config.flask_port} (debug={config.flask_debug})")
    print(f"  Workers: {config.max_workers}")
    print(f"  Log Level: {config.log_level}")
    print(f"  Max Upload: {config.max_upload_size_mb}MB")
    print(f"  Task Retention: {config.task_retention_seconds}s")
