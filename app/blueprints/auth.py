"""
认证蓝图 - 登录、注册、API Token 管理
"""

import re
import time
import random
import logging
from flask import Blueprint, request, session, current_app

from app.utils import api_error, api_success
from app.auth_middleware import create_token

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# 注册验证码：邮箱 -> { "code": "123456", "expires_at": timestamp }
_register_codes = {}
# 发码限流：邮箱 -> 上次发送时间
_register_code_last_sent = {}
REGISTER_CODE_EXPIRE = 600  # 10 分钟
REGISTER_CODE_COOLDOWN = 60  # 同一邮箱 60 秒内只能发一次


def _get_current_username():
    """从 session 获取当前用户"""
    return session.get("username")


@auth_bp.route("/login", methods=["POST"])
def login():
    from utils.auth_config import load_config

    data = request.get_json()
    username = (data.get("username") or "").strip().lower()
    password = data.get("password", "")

    if not username or not password:
        return api_error("用户名和密码不能为空", 400)

    try:
        config_path = current_app.config.get("CONFIG_PATH")
        config = load_config(config_path)
        if not config:
            logger.warning("Login: config not loaded, path=%s", config_path)
            return api_error("登录失败: 配置文件无效", 500)
        usernames = config.get("credentials", {}).get("usernames", {})

        if username not in usernames:
            return api_error("用户名或密码错误", 401)

        user = usernames[username]
        if user.get("disabled"):
            return api_error("该账户已被停用，请联系管理员", 401)

        import bcrypt
        stored = user.get("password", "")
        if isinstance(stored, str) and stored.startswith("$2b$"):
            pw_bytes = stored.encode("utf-8")
        else:
            pw_bytes = stored
        if bcrypt.checkpw(password.encode("utf-8"), pw_bytes):
            session["username"] = username
            avatar = user.get("avatar")
            avatar_url = f"/api/avatars/{avatar}" if avatar else None
            user_data = {
                "success": True,
                "username": username,
                "name": user.get("first_name", "") or username,
                "email": user.get("email", ""),
                "roles": user.get("roles", []),
                "avatar": avatar_url,
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
        avatar = user.get("avatar")
        avatar_url = f"/api/avatars/{avatar}" if avatar else None
        return api_success(data={
            "username": username,
            "name": user.get("first_name", "") or username,
            "email": user.get("email", ""),
            "roles": user.get("roles", []),
            "avatar": avatar_url,
        })
    except Exception as e:
        logger.error(f"Get me error: {e}")
        return api_error(str(e), 500)


@auth_bp.route("/profile", methods=["PUT"])
def update_profile():
    """修改当前用户资料：用户名、昵称、邮箱"""
    username = _get_current_username()
    if not username:
        return api_error("未登录", 401)
    from utils.auth_config import load_config, save_config

    data = request.get_json() or {}
    new_username = (data.get("username") or "").strip().lower()
    nickname = (data.get("nickname") or "").strip()
    email = (data.get("email") or "").strip()

    if not new_username:
        return api_error("用户名不能为空", 400)
    if email and not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return api_error("邮箱格式不正确", 400)

    try:
        config_path = current_app.config.get("CONFIG_PATH")
        config = load_config(config_path)
        usernames = config.get("credentials", {}).get("usernames") or {}

        if username not in usernames:
            return api_error("用户不存在", 401)

        user_data = usernames[username].copy()

        # 用户名变更：需检查是否被占用，并重命名 config 中的键
        if new_username != username:
            if new_username in usernames:
                return api_error("该用户名已被使用", 400)
            # 删除旧键，添加新键
            del usernames[username]
            user_data["first_name"] = nickname or new_username
            user_data["email"] = email
            usernames[new_username] = user_data
            # 更新 session
            session["username"] = new_username
            # 若头像存在，需重命名头像文件
            avatar = user_data.get("avatar")
            if avatar:
                import os
                uploads = current_app.config.get("UPLOADS_FOLDER")
                if uploads:
                    old_path = os.path.join(uploads, "avatars", avatar)
                    ext = os.path.splitext(avatar)[1] or ".png"
                    new_avatar_name = f"{new_username}{ext}"
                    new_path = os.path.join(uploads, "avatars", new_avatar_name)
                    if os.path.exists(old_path):
                        try:
                            os.rename(old_path, new_path)
                        except OSError:
                            pass
                    user_data["avatar"] = new_avatar_name
        else:
            user_data["first_name"] = nickname or username
            user_data["email"] = email
            usernames[username] = user_data

        config["credentials"]["usernames"] = usernames
        if not save_config(config_path, config):
            return api_error("保存配置失败", 500)

        return api_success(data={
            "username": session.get("username"),
            "name": user_data.get("first_name", "") or session.get("username"),
            "email": user_data.get("email", ""),
            "avatar": f"/api/avatars/{user_data.get('avatar')}" if user_data.get("avatar") else None,
        }, message="资料已更新")
    except Exception as e:
        logger.error(f"Update profile error: {e}")
        return api_error(str(e), 500)


@auth_bp.route("/password", methods=["PUT"])
def update_password():
    """修改当前用户密码"""
    username = _get_current_username()
    if not username:
        return api_error("未登录", 401)
    from utils.auth_config import load_config, save_config

    data = request.get_json() or {}
    current_password = data.get("current_password", "")
    new_password = (data.get("new_password") or "").strip()
    new_password_repeat = (data.get("new_password_repeat") or "").strip()

    if not current_password:
        return api_error("请输入当前密码", 400)
    if not new_password:
        return api_error("请输入新密码", 400)
    if len(new_password) < 6:
        return api_error("新密码至少 6 位", 400)
    if new_password != new_password_repeat:
        return api_error("两次输入的新密码不一致", 400)

    try:
        import bcrypt
        config_path = current_app.config.get("CONFIG_PATH")
        config = load_config(config_path)
        usernames = config.get("credentials", {}).get("usernames") or {}
        user = usernames.get(username)
        if not user:
            return api_error("用户不存在", 401)

        stored = user.get("password", "")
        pw_bytes = stored.encode("utf-8") if isinstance(stored, str) else stored
        if not bcrypt.checkpw(current_password.encode("utf-8"), pw_bytes):
            return api_error("当前密码错误", 400)

        hashed = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        usernames[username] = {**user, "password": hashed}
        config["credentials"]["usernames"] = usernames
        if not save_config(config_path, config):
            return api_error("保存配置失败", 500)
        return api_success(message="密码已更新")
    except Exception as e:
        logger.error(f"Update password error: {e}")
        return api_error(str(e), 500)


@auth_bp.route("/avatar", methods=["POST"])
def upload_avatar():
    """上传用户头像"""
    username = _get_current_username()
    if not username:
        return api_error("未登录", 401)
    from utils.auth_config import load_config, save_config
    import os

    if "avatar" not in request.files:
        return api_error("未选择文件", 400)
    file = request.files["avatar"]
    if not file or file.filename == "":
        return api_error("未选择文件", 400)

    allowed = {"png", "jpg", "jpeg", "gif", "webp"}
    ext = (file.filename.rsplit(".", 1)[-1] or "").lower()
    if ext not in allowed:
        return api_error("仅支持 PNG、JPG、GIF、WebP 格式", 400)

    uploads = current_app.config.get("UPLOADS_FOLDER")
    if not uploads:
        return api_error("未配置上传目录", 500)

    avatars_dir = os.path.join(uploads, "avatars")
    os.makedirs(avatars_dir, exist_ok=True)

    filename = f"{username}.{ext}"
    filepath = os.path.join(avatars_dir, filename)
    try:
        file.save(filepath)
    except OSError as e:
        logger.error(f"Save avatar error: {e}")
        return api_error("保存文件失败", 500)

    try:
        config_path = current_app.config.get("CONFIG_PATH")
        config = load_config(config_path)
        usernames = config.get("credentials", {}).get("usernames") or {}
        if username not in usernames:
            return api_error("用户不存在", 401)
        usernames[username] = {**usernames[username], "avatar": filename}
        config["credentials"]["usernames"] = usernames
        if not save_config(config_path, config):
            return api_error("保存配置失败", 500)
    except Exception as e:
        logger.error(f"Update config error: {e}")
        return api_error(str(e), 500)

    return api_success(data={"avatar": f"/api/avatars/{filename}"}, message="头像已更新")


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


def _require_admin():
    """确保当前用户为管理员"""
    username = _get_current_username()
    if not username:
        return None, "未登录"
    try:
        from utils.auth_config import load_config, is_admin
        config = load_config(current_app.config.get("CONFIG_PATH"))
        user = (config.get("credentials", {}).get("usernames") or {}).get(username)
        if not user or not is_admin(user.get("roles")):
            return None, "需要管理员权限"
        return username, None
    except Exception as e:
        logger.error(f"Admin check error: {e}")
        return None, str(e)


@auth_bp.route("/users", methods=["GET"])
def list_users():
    """获取用户列表（仅管理员）"""
    _, err = _require_admin()
    if err:
        return api_error(err, 403)

    try:
        from utils.auth_config import load_config
        config = load_config(current_app.config.get("CONFIG_PATH"))
        usernames = config.get("credentials", {}).get("usernames") or {}
        users = []
        for uname, u in usernames.items():
            users.append({
                "username": uname,
                "email": u.get("email", ""),
                "name": u.get("first_name", "") or uname,
                "roles": u.get("roles", []),
                "disabled": bool(u.get("disabled")),
            })
        return api_success(data={"users": users})
    except Exception as e:
        logger.error(f"List users error: {e}")
        return api_error(str(e), 500)


@auth_bp.route("/users", methods=["POST"])
def add_user():
    """添加用户（仅管理员）"""
    _, err = _require_admin()
    if err:
        return api_error(err, 403)

    from utils.auth_config import load_config, save_config

    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    email = (data.get("email") or "").strip()
    password = (data.get("password") or "").strip()
    is_admin_user = bool(data.get("is_admin"))

    if not username:
        return api_error("用户名为空", 400)
    if not password or len(password) < 6:
        return api_error("密码至少 6 位", 400)
    if email and not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return api_error("邮箱格式不正确", 400)

    try:
        import bcrypt
        config_path = current_app.config.get("CONFIG_PATH")
        config = load_config(config_path)
        usernames = config.get("credentials", {}).get("usernames") or {}
        if username in usernames:
            return api_error("用户名已被使用", 400)

        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        usernames[username] = {
            "email": email,
            "first_name": "",
            "last_name": "",
            "password": hashed,
            "roles": ["admin"] if is_admin_user else [],
            "disabled": False,
            "failed_login_attempts": 0,
            "logged_in": False,
        }
        config["credentials"]["usernames"] = usernames
        if not save_config(config_path, config):
            return api_error("保存配置失败", 500)
        return api_success(message="用户已添加")
    except Exception as e:
        logger.error(f"Add user error: {e}")
        return api_error(str(e), 500)


@auth_bp.route("/users/<username>", methods=["PUT"])
def update_user(username):
    """更新用户：启用/停用、设置管理员（仅管理员）"""
    _, err = _require_admin()
    if err:
        return api_error(err, 403)

    from utils.auth_config import load_config, save_config

    data = request.get_json() or {}
    disabled = data.get("disabled")
    is_admin_user = data.get("is_admin")

    try:
        config_path = current_app.config.get("CONFIG_PATH")
        config = load_config(config_path)
        usernames = config.get("credentials", {}).get("usernames") or {}
        if username not in usernames:
            return api_error("用户不存在", 404)

        # 不能修改自己的管理员状态或停用自己
        current = _get_current_username()
        if username == current:
            if disabled:
                return api_error("不能停用自己的账户", 400)
            if is_admin_user is False:
                return api_error("不能取消自己的管理员权限", 400)

        user = usernames[username]
        if disabled is not None:
            user = {**user, "disabled": bool(disabled)}
        if is_admin_user is not None:
            roles = list(user.get("roles") or [])
            from utils.auth_config import ADMIN_ROLE
            if is_admin_user and ADMIN_ROLE not in roles:
                roles.append(ADMIN_ROLE)
            elif not is_admin_user and ADMIN_ROLE in roles:
                roles = [r for r in roles if r != ADMIN_ROLE]
            user = {**user, "roles": roles}
        usernames[username] = user
        config["credentials"]["usernames"] = usernames
        if not save_config(config_path, config):
            return api_error("保存配置失败", 500)
        return api_success(message="已更新")
    except Exception as e:
        logger.error(f"Update user error: {e}")
        return api_error(str(e), 500)


@auth_bp.route("/users/<username>", methods=["DELETE"])
def delete_user(username):
    """删除用户（仅管理员）"""
    _, err = _require_admin()
    if err:
        return api_error(err, 403)

    from utils.auth_config import load_config, save_config

    current = _get_current_username()
    if username == current:
        return api_error("不能删除自己的账户", 400)

    try:
        config_path = current_app.config.get("CONFIG_PATH")
        config = load_config(config_path)
        usernames = config.get("credentials", {}).get("usernames") or {}
        if username not in usernames:
            return api_error("用户不存在", 404)
        del usernames[username]
        config["credentials"]["usernames"] = usernames
        if not save_config(config_path, config):
            return api_error("保存配置失败", 500)
        return api_success(message="已删除")
    except Exception as e:
        logger.error(f"Delete user error: {e}")
        return api_error(str(e), 500)


def _get_register_require_email_verification():
    """是否开启注册邮箱验证码（仅读配置）"""
    try:
        from utils.auth_config import load_config
        cfg = load_config(current_app.config.get("CONFIG_PATH")) or {}
        lab = cfg.get("lab") or {}
        email_cfg = lab.get("email") or {}
        return bool(email_cfg.get("require_verification_for_register")) and bool(email_cfg.get("enabled")) and bool(email_cfg.get("smtp_host"))
    except Exception:
        return False


def _get_email_config_for_send():
    """获取发邮件所需配置（用于发送注册验证码）"""
    try:
        from utils.auth_config import load_config
        cfg = load_config(current_app.config.get("CONFIG_PATH")) or {}
        lab = cfg.get("lab") or {}
        return lab.get("email") or {}
    except Exception:
        return {}


@auth_bp.route("/register-settings", methods=["GET"])
def register_settings():
    """获取注册相关设置（公开，供注册页判断是否需要验证码）"""
    return api_success(data={
        "require_email_verification": _get_register_require_email_verification(),
    })


@auth_bp.route("/send-register-code", methods=["POST"])
def send_register_code():
    """发送注册验证码到邮箱（公开）"""
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return api_error("请填写邮箱", 400)
    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return api_error("邮箱格式不正确", 400)

    if not _get_register_require_email_verification():
        return api_error("当前未开启注册邮箱验证码", 400)

    now = time.time()
    if email in _register_code_last_sent and (now - _register_code_last_sent[email]) < REGISTER_CODE_COOLDOWN:
        return api_error("发送过于频繁，请 60 秒后再试", 429)

    ec = _get_email_config_for_send()
    smtp_host = ec.get("smtp_host") or ""
    smtp_port = int(ec.get("smtp_port") or 587)
    smtp_user = ec.get("smtp_user") or None
    smtp_password = ec.get("smtp_password") or None
    from_email = ec.get("from_email") or None
    use_tls = bool(ec.get("use_tls", True))

    code = "".join(str(random.randint(0, 9)) for _ in range(6))
    _register_codes[email] = {"code": code, "expires_at": now + REGISTER_CODE_EXPIRE}
    _register_code_last_sent[email] = now

    from utils.email_sender import send_email
    ok, msg = send_email(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        to_email=email,
        subject="[Fino] 注册验证码",
        body=f"您的注册验证码为：{code}\n有效期 10 分钟，请勿泄露。",
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        from_email=from_email,
        use_tls=use_tls,
    )
    if not ok:
        del _register_codes[email]
        return api_error(msg or "发送失败", 500)
    return api_success(message="验证码已发送，请查收邮件")


@auth_bp.route("/register", methods=["POST"])
def register():
    from flask import current_app
    from utils.auth_config import load_config, save_config

    data = request.get_json()
    email = (data.get("email") or "").strip()
    username = data.get("username", "").strip().lower()
    password = data.get("password", "").strip()
    password_repeat = data.get("password_repeat", "").strip()
    password_hint = data.get("password_hint", "").strip() or None
    verification_code = (data.get("verification_code") or "").strip()

    if not all([email, username, password, password_repeat]):
        return api_error("所有字段都为必填项", 400)

    if password != password_repeat:
        return api_error("两次输入的密码不一致", 400)

    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return api_error("邮箱格式不正确", 400)

    require_verification = _get_register_require_email_verification()
    if require_verification:
        if not verification_code:
            return api_error("请输入邮箱验证码", 400)
        entry = _register_codes.get(email)
        if not entry:
            return api_error("验证码无效或已过期，请重新获取", 400)
        if entry["code"] != verification_code:
            return api_error("验证码错误", 400)
        if time.time() > entry["expires_at"]:
            _register_codes.pop(email, None)
            return api_error("验证码已过期，请重新获取", 400)
        _register_codes.pop(email, None)

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
