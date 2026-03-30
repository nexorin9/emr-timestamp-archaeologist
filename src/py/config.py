"""
EMR Timestamp Archaeologist - Python 配置管理
使用 python-dotenv 管理环境变量和 API 配置
"""

from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# 项目根目录（src/py 的父目录）
if __name__ == "__main__":
    _PROJECT_ROOT = Path(__file__).parent.parent.parent
else:
    _PROJECT_ROOT = Path(__file__).parent.parent

_CONFIG_DIR = Path.home() / ".emr-archaeologist"
_CACHE_DIR = _CONFIG_DIR / "cache"
_LOG_DIR = _CONFIG_DIR / "logs"
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_ENV_FILE = _PROJECT_ROOT / ".env"


@dataclass
class ApiConfig:
    """API 配置"""
    provider: str = "anthropic"  # openai | anthropic
    api_key: str = ""
    model: str = "claude-sonnet-4-20250514"
    api_base: Optional[str] = None  # 可选的自定义 API 端点

    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass
class LlmConfig:
    """LLM 配置"""
    enabled: bool = True
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: int = 60


@dataclass
class DetectorConfig:
    """检测器配置"""
    batch_threshold_seconds: int = 60
    night_start: int = 22
    night_end: int = 5
    min_batch_size: int = 3
    sequence_rush_minutes: int = 5


@dataclass
class CacheConfig:
    """缓存配置"""
    enabled: bool = True
    ttl_hours: int = 24
    max_size_mb: int = 500


@dataclass
class AppConfig:
    """应用完整配置"""
    version: str = "1.0.0"
    api: ApiConfig = field(default_factory=ApiConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    verbose: bool = False
    log_level: str = "INFO"
    log_file: Optional[str] = None


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_dir: Optional[Path] = None):
        self._config_dir = config_dir or _CONFIG_DIR
        self._cache_dir = _CACHE_DIR
        self._log_dir = _LOG_DIR
        self._config_file = _CONFIG_FILE
        self._env_file = _ENV_FILE
        self._config: Optional[AppConfig] = None
        self._env_loaded = False

    def _ensure_dirs(self) -> None:
        """确保配置目录存在"""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _load_env(self) -> None:
        """加载 .env 文件"""
        if not self._env_loaded:
            if self._env_file.exists():
                load_dotenv(self._env_file, override=True)
            self._env_loaded = True

    def load(self) -> AppConfig:
        """从文件和环境变量加载配置"""
        self._ensure_dirs()
        self._load_env()

        # 优先从 config.json 加载，env 覆盖
        config = self._load_from_file()

        # 从环境变量覆盖
        config = self._apply_env_vars(config)

        self._config = config
        return config

    def _load_from_file(self) -> AppConfig:
        """从 JSON 文件加载配置"""
        if not self._config_file.exists():
            return AppConfig()

        try:
            with open(self._config_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            api_cfg = ApiConfig(**data.get("api", {}))
            llm_cfg = LlmConfig(**data.get("llm", {}))
            detector_cfg = DetectorConfig(**data.get("detector", {}))
            cache_cfg = CacheConfig(**data.get("cache", {}))

            return AppConfig(
                version=data.get("version", "1.0.0"),
                api=api_cfg,
                llm=llm_cfg,
                detector=detector_cfg,
                cache=cache_cfg,
                verbose=data.get("verbose", False),
                log_level=data.get("log_level", "INFO"),
                log_file=data.get("log_file"),
            )
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            sys.stderr.write(f"警告: 配置文件格式错误，使用默认配置: {e}\n")
            return AppConfig()

    def _apply_env_vars(self, config: AppConfig) -> AppConfig:
        """应用环境变量到配置"""
        # API 配置
        if os.getenv("EMR_API_PROVIDER"):
            config.api.provider = os.getenv("EMR_API_PROVIDER")
        if os.getenv("EMR_API_KEY"):
            config.api.api_key = os.getenv("EMR_API_KEY")
        if os.getenv("EMR_API_MODEL"):
            config.api.model = os.getenv("EMR_API_MODEL")
        if os.getenv("EMR_API_BASE"):
            config.api.api_base = os.getenv("EMR_API_BASE")

        # LLM 配置
        if os.getenv("EMR_LLM_ENABLED"):
            config.llm.enabled = os.getenv("EMR_LLM_ENABLED").lower() in ("1", "true", "yes")
        if os.getenv("EMR_LLM_TEMPERATURE"):
            config.llm.temperature = float(os.getenv("EMR_LLM_TEMPERATURE", "0.3"))
        if os.getenv("EMR_LLM_MAX_TOKENS"):
            config.llm.max_tokens = int(os.getenv("EMR_LLM_MAX_TOKENS", "4096"))
        if os.getenv("EMR_LLM_TIMEOUT"):
            config.llm.timeout = int(os.getenv("EMR_LLM_TIMEOUT", "60"))

        # 检测器配置
        if os.getenv("EMR_BATCH_THRESHOLD"):
            config.detector.batch_threshold_seconds = int(os.getenv("EMR_BATCH_THRESHOLD", "60"))
        if os.getenv("EMR_NIGHT_START"):
            config.detector.night_start = int(os.getenv("EMR_NIGHT_START", "22"))
        if os.getenv("EMR_NIGHT_END"):
            config.detector.night_end = int(os.getenv("EMR_NIGHT_END", "5"))

        # 通用配置
        if os.getenv("EMR_VERBOSE"):
            config.verbose = os.getenv("EMR_VERBOSE", "").lower() in ("1", "true", "yes")
        if os.getenv("EMR_LOG_LEVEL"):
            config.log_level = os.getenv("EMR_LOG_LEVEL", "INFO")

        return config

    def save(self, config: Optional[AppConfig] = None) -> None:
        """保存配置到文件"""
        self._ensure_dirs()
        if config is None:
            config = self._config or self.load()

        data = {
            "version": config.version,
            "api": {
                "provider": config.api.provider,
                "api_key": config.api.api_key,
                "model": config.api.model,
                "api_base": config.api.api_base,
            },
            "llm": {
                "enabled": config.llm.enabled,
                "temperature": config.llm.temperature,
                "max_tokens": config.llm.max_tokens,
                "timeout": config.llm.timeout,
            },
            "detector": {
                "batch_threshold_seconds": config.detector.batch_threshold_seconds,
                "night_start": config.detector.night_start,
                "night_end": config.detector.night_end,
                "min_batch_size": config.detector.min_batch_size,
                "sequence_rush_minutes": config.detector.sequence_rush_minutes,
            },
            "cache": {
                "enabled": config.cache.enabled,
                "ttl_hours": config.cache.ttl_hours,
                "max_size_mb": config.cache.max_size_mb,
            },
            "verbose": config.verbose,
            "log_level": config.log_level,
            "log_file": config.log_file,
        }

        with open(self._config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项（支持点号路径，如 api.provider）"""
        if self._config is None:
            self.load()

        parts = key.split(".")
        value: Any = self._config
        for part in parts:
            if hasattr(value, part):
                value = getattr(value, part)
            elif isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """设置配置项（支持点号路径）"""
        if self._config is None:
            self.load()

        parts = key.split(".")
        target: Any = self._config
        for part in parts[:-1]:
            if hasattr(target, part):
                target = getattr(target, part)
            elif isinstance(target, dict) and part in target:
                target = target[part]
            else:
                raise KeyError(f"配置路径不存在: {key}")

        final_key = parts[-1]
        if hasattr(target, final_key):
            setattr(target, final_key, value)
        elif isinstance(target, dict):
            target[final_key] = value
        else:
            raise KeyError(f"配置路径不存在: {key}")

    def get_config(self) -> AppConfig:
        """获取完整配置对象"""
        if self._config is None:
            self.load()
        return self._config

    def get_cache_dir(self) -> Path:
        """获取缓存目录"""
        self._ensure_dirs()
        return self._cache_dir

    def get_log_dir(self) -> Path:
        """获取日志目录"""
        self._ensure_dirs()
        return self._log_dir

    def validate_api_key(self) -> tuple[bool, str]:
        """
        验证 API key 是否已配置
        Returns: (is_valid, message)
        """
        if self._config is None:
            self.load()

        api_key = self._config.api.api_key
        provider = self._config.api.provider

        if not api_key:
            return False, "API key 未设置。请运行 config set api.api_key <your_key> 或设置 EMR_API_KEY 环境变量"

        # 简单格式验证
        if provider == "anthropic":
            if not api_key.startswith("sk-ant-"):
                return False, "Anthropic API key 格式错误，应以 sk-ant- 开头"
        elif provider == "openai":
            if not api_key.startswith("sk-"):
                return False, "OpenAI API key 格式错误，应以 sk- 开头"

        return True, "API key 格式正确"

    def reset(self) -> None:
        """重置配置为默认"""
        self._config = AppConfig()
        if self._config_file.exists():
            self._config_file.unlink()


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例"""
    return ConfigManager()


# 便捷函数
def get_cache_dir() -> Path:
    """获取缓存目录"""
    return get_config_manager().get_cache_dir()


def get_log_dir() -> Path:
    """获取日志目录"""
    return get_config_manager().get_log_dir()


if __name__ == "__main__":
    # 测试配置加载
    cm = ConfigManager()
    cfg = cm.load()
    print(f"版本: {cfg.version}")
    print(f"API Provider: {cfg.api.provider}")
    print(f"API Key 设置: {cfg.api.is_configured()}")
    print(f"缓存目录: {cm.get_cache_dir()}")
    print(f"日志目录: {cm.get_log_dir()}")
    valid, msg = cm.validate_api_key()
    print(f"API Key 验证: {valid} - {msg}")
