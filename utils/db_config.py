"""
数据库配置模块
从 config.yaml 读取数据库配置，支持 SQLite 和 PostgreSQL
"""

import os
import yaml
from typing import Dict, Any, Optional

# 默认配置路径（与 app.py 一致）
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "conf", "config.yaml")


def load_database_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    从 config.yaml 加载数据库配置

    Returns:
        dict: 数据库配置，包含 type, sqlite, postgresql 等
    """
    path = config_path or DEFAULT_CONFIG_PATH
    config = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                full_config = yaml.safe_load(f)
            config = (full_config or {}).get("database") or {}
        except Exception:
            pass
    return config


def get_database_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    获取数据库配置，返回合并后的默认值

    Returns:
        dict: {
            "type": "sqlite" | "postgresql" | "d1",
            "sqlite": {"path": "investment.db"},
            "postgresql": {...},
            "d1": {"account_id": "", "database_id": "", "api_token": ""}
        }
    """
    cfg = load_database_config(config_path)
    return {
        "type": cfg.get("type") or "sqlite",
        "sqlite": {
            "path": (cfg.get("sqlite") or {}).get("path") or "investment.db",
        },
        "postgresql": {
            "host": (cfg.get("postgresql") or {}).get("host") or "localhost",
            "port": int((cfg.get("postgresql") or {}).get("port") or 5432),
            "database": (cfg.get("postgresql") or {}).get("database") or "investment",
            "user": (cfg.get("postgresql") or {}).get("user") or "postgres",
            "password": (cfg.get("postgresql") or {}).get("password") or "",
            "sslmode": (cfg.get("postgresql") or {}).get("sslmode") or "prefer",
        },
        "d1": {
            "account_id": (cfg.get("d1") or {}).get("account_id") or "",
            "database_id": (cfg.get("d1") or {}).get("database_id") or "",
            "api_token": (cfg.get("d1") or {}).get("api_token") or "",
        },
    }


def test_d1_connection(
    account_id: str = "",
    database_id: str = "",
    api_token: str = "",
) -> tuple[bool, str]:
    """
    测试 Cloudflare D1 数据库连接

    Returns:
        tuple[bool, str]: (是否成功, 消息)
    """
    if not account_id or not database_id or not api_token:
        return False, "请填写 Account ID、Database ID 和 API Token"
    try:
        import urllib.request
        import json
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"
        req = urllib.request.Request(
            url,
            data=json.dumps({"sql": "SELECT 1"}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data.get("success"):
            return True, "✅ 连接成功！"
        errs = data.get("errors", [])
        msg = errs[0].get("message", "未知错误") if errs else "连接失败"
        return False, f"❌ 连接失败：{msg}"
    except Exception as e:
        return False, f"❌ 连接失败：{str(e)}"


def test_postgresql_connection(
    host: str = "localhost",
    port: int = 5432,
    database: str = "investment",
    user: str = "postgres",
    password: str = "",
    sslmode: str = "prefer",
) -> tuple[bool, str]:
    """
    测试 PostgreSQL 数据库连接

    Returns:
        tuple[bool, str]: (是否成功, 消息)
    """
    try:
        import psycopg2
    except ImportError:
        return False, "未安装 psycopg2，请执行: pip install psycopg2-binary"
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=database,
            user=user,
            password=password,
            sslmode=sslmode,
            connect_timeout=5,
        )
        conn.close()
        return True, "✅ 连接成功！"
    except Exception as e:
        return False, f"❌ 连接失败：{str(e)}"


def save_database_config(
    db_type: str,
    sqlite_path: str = "investment.db",
    pg_host: str = "localhost",
    pg_port: int = 5432,
    pg_database: str = "investment",
    pg_user: str = "postgres",
    pg_password: str = "",
    pg_sslmode: str = "prefer",
    d1_account_id: str = "",
    d1_database_id: str = "",
    d1_api_token: str = "",
    config_path: Optional[str] = None,
) -> bool:
    """
    保存数据库配置到 config.yaml

    Returns:
        bool: 是否保存成功
    """
    path = config_path or DEFAULT_CONFIG_PATH
    try:
        full_config = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                full_config = yaml.safe_load(f) or {}
        full_config["database"] = {
            "type": db_type,
            "sqlite": {"path": sqlite_path},
            "postgresql": {
                "host": pg_host,
                "port": pg_port,
                "database": pg_database,
                "user": pg_user,
                "password": pg_password,
                "sslmode": pg_sslmode,
            },
            "d1": {
                "account_id": d1_account_id,
                "database_id": d1_database_id,
                "api_token": d1_api_token,
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(full_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return True
    except Exception:
        return False
