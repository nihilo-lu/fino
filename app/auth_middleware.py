"""
认证中间件 - JWT Token 验证
"""

import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import request, g

logger = logging.getLogger(__name__)


def get_jwt_secret():
    """从配置获取 JWT 密钥"""
    from flask import current_app
    config_path = current_app.config.get("CONFIG_PATH")
    if config_path:
        try:
            from utils.auth_config import load_config
            config = load_config(config_path)
            if config:
                return config.get("cookie", {}).get("key", "investment_tracker_secret")
        except Exception:
            pass
    return "investment_tracker_secret"


def create_token(username: str, expiry_days: int | None = 30) -> str:
    """创建 JWT Token。expiry_days 为 None 或 0 时表示永久有效"""
    try:
        import jwt
    except ImportError:
        logger.warning("PyJWT 未安装，使用简单 token。请运行: pip install PyJWT")
        # 简单回退：不签名，仅 base64 编码
        import base64
        import json
        payload = {"username": username}
        if expiry_days is not None and expiry_days > 0:
            payload["exp"] = (datetime.utcnow() + timedelta(days=expiry_days)).timestamp()
        return base64.b64encode(json.dumps(payload).encode()).decode()

    secret = get_jwt_secret()
    payload = {
        "username": username,
        "iat": datetime.utcnow(),
    }
    if expiry_days is not None and expiry_days > 0:
        payload["exp"] = datetime.utcnow() + timedelta(days=expiry_days)
    return jwt.encode(payload, secret, algorithm="HS256")


def _decode_token(token: str) -> dict | None:
    """解码 JWT Token，不校验是否存在于配置"""
    if not token:
        return None
    try:
        import jwt
    except ImportError:
        import base64
        import json
        try:
            payload = json.loads(base64.b64decode(token).decode())
            username = payload.get("username")
            if not username:
                return None
            exp = payload.get("exp")
            if exp is not None and datetime.utcnow().timestamp() >= exp:
                return None
            return payload
        except Exception:
            return None

    try:
        secret = get_jwt_secret()
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except Exception:
        return None


def verify_token(token: str) -> dict | None:
    """验证 API Token：解码且需匹配配置中存储的 token（退出登录、改密码不影响）"""
    if not token:
        return None
    payload = _decode_token(token)
    if not payload:
        return None
    username = payload.get("username")
    if not username:
        return None
    # 校验 token 是否与配置中存储的一致
    from flask import current_app
    config_path = current_app.config.get("CONFIG_PATH")
    if config_path:
        try:
            from utils.auth_config import load_config
            config = load_config(config_path)
            usernames = (config.get("credentials") or {}).get("usernames") or {}
            stored = usernames.get(username, {}).get("api_token")
            if stored and stored == token:
                return payload
        except Exception:
            pass
    return None


def get_token_from_request() -> str | None:
    """从请求头获取 Token：Authorization: Bearer <token>"""
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def login_required(f):
    """需要登录的装饰器，验证通过后将 g.current_user 设为 payload"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_request()
        payload = verify_token(token) if token else None
        if not payload:
            from app.utils import api_error
            return api_error("未登录或 Token 已过期", 401)
        g.current_user = payload
        return f(*args, **kwargs)
    return decorated


def optional_login(f):
    """可选登录装饰器，有 token 则验证并设置 g.current_user，无 token 则 g.current_user 为 None"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_request()
        payload = verify_token(token) if token else None
        g.current_user = payload
        return f(*args, **kwargs)
    return decorated
