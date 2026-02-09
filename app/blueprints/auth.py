"""
认证蓝图 - 登录、注册、API Token 管理
"""

import re
import logging
from flask import Blueprint, request, session, current_app

from app.utils import api_error, api_success
from app.auth_middleware import create_token

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _get_current_username():
    """从 session 获取当前用户"""
    return session.get("username")


@auth_bp.route("/login", methods=["POST"])
def login():
    from utils.auth_config import load_config

    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return api_error("用户名和密码不能为空", 400)

    try:
        config_path = current_app.config.get("CONFIG_PATH")
        config = load_config(config_path)
        usernames = config.get("credentials", {}).get("usernames", {})

        if username not in usernames:
            return api_error("用户名或密码错误", 401)

        user = usernames[username]
        import bcrypt
        stored = user.get("password", "")
        if isinstance(stored, str) and stored.startswith("$2b$"):
            pw_bytes = stored.encode("utf-8")
        else:
            pw_bytes = stored
        if bcrypt.checkpw(password.encode("utf-8"), pw_bytes):
            session["username"] = username
            user_data = {
                "success": True,
                "username": username,
                "name": user.get("first_name", "") or username,
                "email": user.get("email", ""),
                "roles": user.get("roles", []),
            }
            return api_success(data=user_data)
        return api_error("用户名或密码错误", 401)
    except Exception as e:
        logger.error(f"Login error: {e}")
        return api_error(f"登录失败: {str(e)}", 500)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("username", None)
    return api_success(message="已退出登录")


@auth_bp.route("/me", methods=["GET"])
def me():
    """获取当前登录用户信息（用于 session 校验）"""
    username = _get_current_username()
    if not username:
        return api_error("未登录", 401)
    try:
        from utils.auth_config import load_config
        config = load_config(current_app.config.get("CONFIG_PATH"))
        user = (config.get("credentials", {}).get("usernames") or {}).get(username)
        if not user:
            return api_error("用户不存在", 401)
        return api_success(data={
            "username": username,
            "name": user.get("first_name", "") or username,
            "email": user.get("email", ""),
            "roles": user.get("roles", []),
        })
    except Exception as e:
        logger.error(f"Get me error: {e}")
        return api_error(str(e), 500)


@auth_bp.route("/token", methods=["GET"])
def get_token():
    """获取当前用户的 API Token（未生成则返回空）"""
    username = _get_current_username()
    if not username:
        return api_error("未登录", 401)
    try:
        from utils.auth_config import load_config
        config = load_config(current_app.config.get("CONFIG_PATH"))
        user = (config.get("credentials", {}).get("usernames") or {}).get(username)
        token = (user or {}).get("api_token")
        return api_success(data={"token": token or ""})
    except Exception as e:
        logger.error(f"Get token error: {e}")
        return api_error(str(e), 500)


def _generate_and_store_token(username: str) -> str:
    """生成 Token 并写入配置"""
    from flask import current_app
    from utils.auth_config import load_config, save_config

    token = create_token(username, expiry_days=None)
    config_path = current_app.config.get("CONFIG_PATH")
    config = load_config(config_path)
    usernames = config.get("credentials", {}).get("usernames", {})
    if username not in usernames:
        raise ValueError("用户不存在")
    usernames[username] = usernames[username].copy()
    usernames[username]["api_token"] = token
    config["credentials"]["usernames"] = usernames
    if not save_config(config_path, config):
        raise RuntimeError("保存配置失败")
    return token


@auth_bp.route("/token/generate", methods=["POST"])
def generate_token():
    """生成 API Token"""
    username = _get_current_username()
    if not username:
        return api_error("未登录", 401)
    try:
        token = _generate_and_store_token(username)
        return api_success(data={"token": token}, message="Token 生成成功")
    except ValueError as e:
        return api_error(str(e), 400)
    except Exception as e:
        logger.error(f"Generate token error: {e}")
        return api_error(str(e), 500)


@auth_bp.route("/token/reset", methods=["POST"])
def reset_token():
    """重置 API Token"""
    username = _get_current_username()
    if not username:
        return api_error("未登录", 401)
    try:
        token = _generate_and_store_token(username)
        return api_success(data={"token": token}, message="Token 已重置")
    except ValueError as e:
        return api_error(str(e), 400)
    except Exception as e:
        logger.error(f"Reset token error: {e}")
        return api_error(str(e), 500)


@auth_bp.route("/register", methods=["POST"])
def register():
    from flask import current_app
    from utils.auth_config import load_config, save_config

    data = request.get_json()
    email = data.get("email", "").strip()
    username = data.get("username", "").strip().lower()
    password = data.get("password", "").strip()
    password_repeat = data.get("password_repeat", "").strip()
    password_hint = data.get("password_hint", "").strip() or None

    if not all([email, username, password, password_repeat]):
        return api_error("所有字段都为必填项", 400)

    if password != password_repeat:
        return api_error("两次输入的密码不一致", 400)

    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return api_error("邮箱格式不正确", 400)

    try:
        config_path = current_app.config.get("CONFIG_PATH")
        config = load_config(config_path)
        usernames = config.get("credentials", {}).get("usernames", {})

        if username in usernames:
            return api_error("用户名已被使用", 400)

        import bcrypt
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        usernames[username] = {
            "email": email,
            "first_name": "",
            "last_name": "",
            "password": hashed,
            "password_hint": password_hint,
            "roles": [],
            "failed_login_attempts": 0,
            "logged_in": False,
        }

        config["credentials"]["usernames"] = usernames

        if save_config(config_path, config):
            return api_success(message="注册成功")
        return api_error("保存配置失败", 500)
    except Exception as e:
        logger.error(f"Register error: {e}")
        return api_error(f"注册失败: {str(e)}", 500)
