"""
认证蓝图 - 登录、注册
"""

import re
import logging
from flask import Blueprint, request

from app.utils import cors_jsonify

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/login", methods=["POST"])
def login():
    from app.extensions import get_db
    from flask import current_app
    from utils.auth_config import load_config

    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return cors_jsonify({"error": "用户名和密码不能为空"}, 400)

    try:
        config_path = current_app.config.get("CONFIG_PATH")
        config = load_config(config_path)
        usernames = config.get("credentials", {}).get("usernames", {})

        if username not in usernames:
            return cors_jsonify({"error": "用户名或密码错误"}, 401)

        user = usernames[username]
        import bcrypt
        stored = user.get("password", "")
        if isinstance(stored, str) and stored.startswith("$2b$"):
            pw_bytes = stored.encode("utf-8")
        else:
            pw_bytes = stored
        if bcrypt.checkpw(password.encode("utf-8"), pw_bytes):
            return cors_jsonify({
                "success": True,
                "username": username,
                "name": user.get("first_name", "") or username,
                "email": user.get("email", ""),
                "roles": user.get("roles", []),
            })
        return cors_jsonify({"error": "用户名或密码错误"}, 401)
    except Exception as e:
        logger.error(f"Login error: {e}")
        return cors_jsonify({"error": f"登录失败: {str(e)}"}, 500)


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
        return cors_jsonify({"error": "所有字段都为必填项"}, 400)

    if password != password_repeat:
        return cors_jsonify({"error": "两次输入的密码不一致"}, 400)

    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return cors_jsonify({"error": "邮箱格式不正确"}, 400)

    try:
        config_path = current_app.config.get("CONFIG_PATH")
        config = load_config(config_path)
        usernames = config.get("credentials", {}).get("usernames", {})

        if username in usernames:
            return cors_jsonify({"error": "用户名已被使用"}, 400)

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
            return cors_jsonify({"success": True, "message": "注册成功"})
        return cors_jsonify({"error": "保存配置失败"}, 500)
    except Exception as e:
        logger.error(f"Register error: {e}")
        return cors_jsonify({"error": f"注册失败: {str(e)}"}, 500)
