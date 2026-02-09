"""
应用配置模块 - 独立于 Flask 的配置加载与管理
支持从 config.yaml 加载，并可被环境变量覆盖
"""

import os
from pathlib import Path


def get_config_path() -> str:
    """获取默认配置文件路径"""
    base_dir = Path(__file__).resolve().parent.parent
    return str(base_dir / "conf" / "config.yaml")


def load_config_dict(config_path: str | None = None) -> dict:
    """加载 YAML 配置为字典"""
    path = config_path or get_config_path()
    if not path or not os.path.exists(path):
        return {}
    try:
        import yaml
        from yaml.loader import SafeLoader
        with open(path, "r", encoding="utf-8") as f:
            return yaml.load(f, Loader=SafeLoader) or {}
    except Exception:
        return {}


class Config:
    """应用配置类 - 封装配置访问"""

    def __init__(self, config_path: str | None = None):
        self.config_path = config_path or get_config_path()
        self._config = load_config_dict(self.config_path)

    def get(self, key: str, default=None):
        """获取配置项，支持点号路径如 database.type"""
        keys = key.split(".")
        val = self._config
        for k in keys:
            val = val.get(k) if isinstance(val, dict) else default
            if val is None:
                return default
        return val

    def __getitem__(self, key: str):
        return self.get(key)

    @property
    def database_type(self) -> str:
        return self.get("database.type", "sqlite")

    @property
    def sqlite_path(self) -> str:
        return self.get("database.sqlite.path", "investment.db")
