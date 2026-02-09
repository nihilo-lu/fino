"""
认证配置工具：加载/保存 config.yaml、判断管理员、用户增删改
"""

import os
import yaml
from yaml.loader import SafeLoader

# 管理员角色标识
ADMIN_ROLE = "admin"


def load_config(config_path: str) -> dict | None:
    """加载认证配置文件。路径不存在或解析失败时返回 None。"""
    if not config_path or not os.path.exists(config_path):
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.load(f, Loader=SafeLoader)
    except Exception:
        return None


def save_config(config_path: str, config: dict) -> bool:
    """将配置写回 YAML 文件。"""
    if not config_path or not config:
        return False
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return True
    except Exception:
        return False


def is_admin(roles: list | None) -> bool:
    """根据 roles 列表判断是否为管理员。"""
    if not roles:
        return False
    return ADMIN_ROLE in (roles if isinstance(roles, list) else [])


def get_usernames(config: dict) -> list[str]:
    """从 config 中取出所有用户名列表。"""
    cred = config.get("credentials") or {}
    usernames = cred.get("usernames") or {}
    return list(usernames.keys())


def get_user(config: dict, username: str) -> dict | None:
    """获取单个用户信息（不含密码原文）。"""
    usernames = (config.get("credentials") or {}).get("usernames") or {}
    return usernames.get(username)


def ensure_pre_authorized(config: dict) -> dict:
    """确保 config 中存在 pre-authorized 结构。"""
    if "pre-authorized" not in config:
        config["pre-authorized"] = {}
    if "emails" not in config["pre-authorized"]:
        config["pre-authorized"]["emails"] = []
    return config
