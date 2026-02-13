"""
主蓝图 - 健康检查、首页、静态文件、PWA 配置
"""

from datetime import datetime
from flask import Blueprint, send_from_directory, current_app, request, jsonify

from app.utils import api_success, api_error

main_bp = Blueprint("main", __name__)

_DEFAULT_PWA = {
    "name": "投资追踪器",
    "short_name": "投资追踪",
    "description": "投资组合追踪与收益分析工具",
    "theme_color": "#E8A317",
    "background_color": "#ffffff",
    "display": "standalone",
    "icon_192": "/frontend/icons/icon-192.png",
    "icon_512": "/frontend/icons/icon-512.png",
    "favicon": "",
}


def _get_pwa_config():
    """从 config.yaml 读取 PWA 配置，合并默认值"""
    try:
        from utils.auth_config import load_config
        cfg = load_config(current_app.config.get("CONFIG_PATH"))
        pwa = (cfg or {}).get("pwa") or {}
        out = _DEFAULT_PWA.copy()
        for k, v in pwa.items():
            if v is not None and v != "":
                out[k] = v
        return out
    except Exception:
        return _DEFAULT_PWA


@main_bp.route("/api/health", methods=["GET"])
def health_check():
    return api_success(data={"status": "ok", "timestamp": datetime.now().isoformat()})


def _parse_version(v):
    """解析语义化版本为 (major, minor, patch) 元组"""
    if not v:
        return (0, 0, 0)
    s = str(v).lstrip("vV")
    parts = s.split(".")[:3]
    try:
        return tuple(int(p) if p.isdigit() else 0 for p in (parts + ["0", "0", "0"])[:3])
    except (ValueError, TypeError):
        return (0, 0, 0)


def _version_lt(current, latest):
    """判断 current 是否小于 latest"""
    return _parse_version(current) < _parse_version(latest)


@main_bp.route("/api/version", methods=["GET"])
def get_version():
    """获取当前版本（需登录）"""
    from flask import session
    if not session.get("username"):
        return api_error("未登录", 401)
    from app import __version__
    return api_success(data={"version": __version__})


@main_bp.route("/api/check-update", methods=["GET"])
def check_update():
    """检测是否有新版本（需登录，从 GitHub Releases 获取）"""
    from flask import session
    if not session.get("username"):
        return api_error("未登录", 401)
    from app import __version__
    current = __version__
    latest = None
    release_url = None
    release_notes = None
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.github.com/repos/nihilo-lu/fino/releases/latest",
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "fino-check-update"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        import json
        obj = json.loads(data)
        latest = obj.get("tag_name", "").lstrip("vV")
        release_url = obj.get("html_url", "")
        release_notes = (obj.get("body") or "")[:500]
    except Exception:
        pass
    if not latest:
        return api_success(data={
            "current": current,
            "latest": current,
            "has_update": False,
            "release_url": None,
            "release_notes": None,
        })
    has_update = _version_lt(current, latest)
    return api_success(data={
        "current": current,
        "latest": latest,
        "has_update": has_update,
        "release_url": release_url,
        "release_notes": release_notes,
    })


@main_bp.route("/api/pwa/config", methods=["GET"])
def get_pwa_config():
    """获取 PWA 配置（公开，供 manifest 和前端使用）"""
    return api_success(data=_get_pwa_config())


@main_bp.route("/api/database/config", methods=["GET"])
def get_database_config():
    """获取数据库配置（仅管理员）"""
    from flask import session
    if not session.get("username"):
        return api_error("未登录", 401)
    from utils.auth_config import load_config, is_admin, get_user
    cfg = load_config(current_app.config.get("CONFIG_PATH"))
    user = get_user(cfg or {}, session["username"])
    if not is_admin(user.get("roles")):
        return api_error("仅管理员可查看", 403)
    try:
        from utils.db_config import get_database_config
        db_cfg = get_database_config(current_app.config.get("CONFIG_PATH"))
        # 不返回 api_token 全文，仅返回掩码
        out = {
            "type": db_cfg["type"],
            "sqlite": db_cfg["sqlite"],
            "postgresql": db_cfg["postgresql"],
            "d1": {
                "account_id": db_cfg["d1"]["account_id"],
                "database_id": db_cfg["d1"]["database_id"],
                "api_token": "***" if db_cfg["d1"]["api_token"] else "",
            },
        }
        return api_success(data=out)
    except Exception as e:
        return api_error(str(e), 500)


@main_bp.route("/api/database/config", methods=["PUT"])
def save_database_config():
    """保存数据库配置（仅管理员）"""
    from flask import session
    if not session.get("username"):
        return api_error("未登录", 401)
    from utils.auth_config import load_config, is_admin, get_user
    cfg = load_config(current_app.config.get("CONFIG_PATH"))
    user = get_user(cfg or {}, session["username"])
    if not is_admin(user.get("roles")):
        return api_error("仅管理员可修改", 403)
    try:
        from utils.db_config import save_database_config as save_db_cfg, get_database_config as get_db_cfg
        body = request.get_json() or {}
        db_type = body.get("type", "sqlite")
        d1_cfg = body.get("d1", {})
        d1_token = d1_cfg.get("api_token", "")
        if d1_token == "***" or (not d1_token and db_type == "d1"):
            # 保留原有 token（前端返回掩码时）
            current = get_db_cfg(current_app.config.get("CONFIG_PATH"))
            d1_token = current.get("d1", {}).get("api_token", "")
        saved = save_db_cfg(
            db_type=db_type,
            sqlite_path=body.get("sqlite", {}).get("path", "investment.db"),
            pg_host=body.get("postgresql", {}).get("host", "localhost"),
            pg_port=int(body.get("postgresql", {}).get("port", 5432)),
            pg_database=body.get("postgresql", {}).get("database", "investment"),
            pg_user=body.get("postgresql", {}).get("user", "postgres"),
            pg_password=body.get("postgresql", {}).get("password", ""),
            pg_sslmode=body.get("postgresql", {}).get("sslmode", "prefer"),
            d1_account_id=d1_cfg.get("account_id", ""),
            d1_database_id=d1_cfg.get("database_id", ""),
            d1_api_token=d1_token,
            config_path=current_app.config.get("CONFIG_PATH"),
        )
        if not saved:
            return api_error("保存配置失败", 500)
        return api_success(message="数据库配置已保存，请重启应用生效")
    except Exception as e:
        return api_error(str(e), 500)


@main_bp.route("/api/database/test", methods=["POST"])
def test_database_connection():
    """测试数据库连接（仅管理员）"""
    from flask import session
    if not session.get("username"):
        return api_error("未登录", 401)
    from utils.auth_config import load_config, is_admin, get_user
    cfg = load_config(current_app.config.get("CONFIG_PATH"))
    user = get_user(cfg or {}, session["username"])
    if not is_admin(user.get("roles")):
        return api_error("仅管理员可测试", 403)
    try:
        body = request.get_json() or {}
        db_type = body.get("type", "sqlite")
        if db_type == "postgresql":
            from utils.db_config import test_postgresql_connection
            pg = body.get("postgresql", {})
            ok, msg = test_postgresql_connection(
                host=pg.get("host", "localhost"),
                port=int(pg.get("port", 5432)),
                database=pg.get("database", "investment"),
                user=pg.get("user", "postgres"),
                password=pg.get("password", ""),
                sslmode=pg.get("sslmode", "prefer"),
            )
        elif db_type == "d1":
            from utils.db_config import test_d1_connection
            d1 = body.get("d1", {})
            ok, msg = test_d1_connection(
                account_id=d1.get("account_id", ""),
                database_id=d1.get("database_id", ""),
                api_token=d1.get("api_token", ""),
            )
        else:
            ok = True
            msg = "SQLite 无需远程连接测试"
        return api_success(data={"ok": ok, "message": msg})
    except Exception as e:
        return api_error(str(e), 500)


@main_bp.route("/api/pwa/config", methods=["PUT"])
def save_pwa_config():
    """保存 PWA 配置（需登录）"""
    from flask import session
    if not session.get("username"):
        return api_error("未登录", 401)
    try:
        from utils.auth_config import load_config, save_config
        body = request.get_json() or {}
        cfg = load_config(current_app.config.get("CONFIG_PATH")) or {}
        if "pwa" not in cfg:
            cfg["pwa"] = {}
        allowed = {"name", "short_name", "description", "theme_color", "background_color", "display", "icon_192", "icon_512", "favicon"}
        for k, v in body.items():
            if k in allowed and v is not None:
                cfg["pwa"][k] = str(v).strip() if isinstance(v, str) else v
        if not save_config(current_app.config.get("CONFIG_PATH"), cfg):
            return api_error("保存配置失败", 500)
        return api_success(data=_get_pwa_config(), message="PWA 配置已保存")
    except Exception as e:
        return api_error(str(e), 500)


@main_bp.route("/api/settings/plugin-center", methods=["GET"])
def get_plugin_center_setting():
    """获取插件中心是否开启（需登录）"""
    from flask import session
    if not session.get("username"):
        return api_error("未登录", 401)
    try:
        from utils.auth_config import load_config
        cfg = load_config(current_app.config.get("CONFIG_PATH")) or {}
        lab = cfg.get("lab") or {}
        enabled = lab.get("plugin_center_enabled", True)
        return api_success(data={"enabled": bool(enabled)})
    except Exception as e:
        return api_error(str(e), 500)


@main_bp.route("/api/settings/plugin-center", methods=["PUT"])
def save_plugin_center_setting():
    """保存插件中心开关（仅管理员）"""
    from flask import session
    if not session.get("username"):
        return api_error("未登录", 401)
    from utils.auth_config import load_config, save_config, is_admin, get_user
    cfg = load_config(current_app.config.get("CONFIG_PATH"))
    user = get_user(cfg or {}, session["username"])
    if not is_admin(user.get("roles")):
        return api_error("仅管理员可修改", 403)
    try:
        cfg = cfg or {}
        if "lab" not in cfg:
            cfg["lab"] = {}
        body = request.get_json() or {}
        cfg["lab"]["plugin_center_enabled"] = bool(body.get("enabled", True))
        if not save_config(current_app.config.get("CONFIG_PATH"), cfg):
            return api_error("保存配置失败", 500)
        return api_success(data={"enabled": cfg["lab"]["plugin_center_enabled"]}, message="已保存")
    except Exception as e:
        return api_error(str(e), 500)


_DEFAULT_EMAIL = {
    "enabled": False,
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_password": "",
    "from_email": "",
    "use_tls": True,
    "require_verification_for_register": False,
}


def _get_email_config():
    """从 config.yaml 读取邮件配置，合并默认值"""
    try:
        from utils.auth_config import load_config
        cfg = load_config(current_app.config.get("CONFIG_PATH"))
        lab = (cfg or {}).get("lab") or {}
        email = lab.get("email") or {}
        out = _DEFAULT_EMAIL.copy()
        for k, v in email.items():
            if k in out and v is not None:
                if k == "smtp_port":
                    try:
                        out[k] = int(v)
                    except (TypeError, ValueError):
                        out[k] = 587
                elif k == "use_tls":
                    out[k] = bool(v)
                elif k == "require_verification_for_register":
                    out[k] = bool(v)
                else:
                    out[k] = v
        return out
    except Exception:
        return _DEFAULT_EMAIL.copy()


@main_bp.route("/api/settings/email", methods=["GET"])
def get_email_config():
    """获取邮件配置（仅管理员）"""
    from flask import session
    if not session.get("username"):
        return api_error("未登录", 401)
    from utils.auth_config import load_config, is_admin, get_user
    cfg = load_config(current_app.config.get("CONFIG_PATH"))
    user = get_user(cfg or {}, session["username"])
    if not is_admin(user.get("roles")):
        return api_error("仅管理员可查看", 403)
    data = _get_email_config()
    if data.get("smtp_password"):
        data["smtp_password"] = "***"
    return api_success(data=data)


@main_bp.route("/api/settings/email", methods=["PUT"])
def save_email_config():
    """保存邮件配置（仅管理员）"""
    from flask import session
    if not session.get("username"):
        return api_error("未登录", 401)
    from utils.auth_config import load_config, save_config, is_admin, get_user
    cfg = load_config(current_app.config.get("CONFIG_PATH"))
    user = get_user(cfg or {}, session["username"])
    if not is_admin(user.get("roles")):
        return api_error("仅管理员可修改", 403)
    try:
        cfg = cfg or {}
        if "lab" not in cfg:
            cfg["lab"] = {}
        if "email" not in cfg["lab"]:
            cfg["lab"]["email"] = {}
        body = request.get_json() or {}
        allowed = {"enabled", "smtp_host", "smtp_port", "smtp_user", "smtp_password", "from_email", "use_tls", "require_verification_for_register"}
        for k in allowed:
            if k in body:
                v = body[k]
                if k == "smtp_password":
                    if v and v != "***":
                        cfg["lab"]["email"][k] = v
                elif k == "smtp_port":
                    try:
                        cfg["lab"]["email"][k] = int(v) if v is not None else 587
                    except (TypeError, ValueError):
                        cfg["lab"]["email"][k] = 587
                elif k in ("use_tls", "enabled", "require_verification_for_register"):
                    cfg["lab"]["email"][k] = bool(v)
                else:
                    cfg["lab"]["email"][k] = str(v).strip() if v is not None else ""
        if not save_config(current_app.config.get("CONFIG_PATH"), cfg):
            return api_error("保存配置失败", 500)
        data = _get_email_config()
        if data.get("smtp_password"):
            data["smtp_password"] = "***"
        return api_success(data=data, message="邮件配置已保存")
    except Exception as e:
        return api_error(str(e), 500)


@main_bp.route("/api/settings/email/test", methods=["POST"])
def send_test_email():
    """发送测试邮件（仅管理员）"""
    from flask import session
    if not session.get("username"):
        return api_error("未登录", 401)
    from utils.auth_config import load_config, is_admin, get_user
    cfg = load_config(current_app.config.get("CONFIG_PATH"))
    user = get_user(cfg or {}, session["username"])
    if not is_admin(user.get("roles")):
        return api_error("仅管理员可操作", 403)
    body = request.get_json() or {}
    to_email = (body.get("to_email") or "").strip() or (user.get("email") or "").strip()
    if not to_email:
        return api_error("请填写收件邮箱或在个人资料中设置邮箱", 400)
    import re
    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", to_email):
        return api_error("邮箱格式不正确", 400)
    ec = _get_email_config()
    if not ec.get("enabled") or not ec.get("smtp_host"):
        return api_error("请先启用并保存邮件配置", 400)
    # 密码可能在前端被掩码，需要从当前 config 读取真实密码
    lab = (cfg or {}).get("lab") or {}
    lab_email = lab.get("email") or {}
    smtp_password = lab_email.get("smtp_password") or ""
    from utils.email_sender import send_email
    ok, msg = send_email(
        smtp_host=ec["smtp_host"],
        smtp_port=int(ec.get("smtp_port", 587)),
        to_email=to_email,
        subject="[Fino] 测试邮件",
        body="这是一封来自 Fino 的测试邮件。如果您收到此邮件，说明邮件配置正确，可用于注册验证码等功能。",
        smtp_user=ec.get("smtp_user") or None,
        smtp_password=smtp_password if smtp_password and smtp_password != "***" else None,
        from_email=ec.get("from_email") or None,
        use_tls=bool(ec.get("use_tls", True)),
    )
    if ok:
        return api_success(message="测试邮件已发送，请查收")
    return api_error(msg or "发送失败", 500)


@main_bp.route("/")
def index():
    if current_app.config.get("API_ONLY"):
        return jsonify({"error": "Not found"}), 404
    return _render_index(_get_pwa_config())


# SPA 子页面路由：刷新时返回 index.html，由前端根据 URL 渲染对应页面
@main_bp.route("/dashboard")
@main_bp.route("/positions")
@main_bp.route("/transactions")
@main_bp.route("/funds")
@main_bp.route("/analysis")
@main_bp.route("/settings")
@main_bp.route("/api-docs")
@main_bp.route("/chat")
def spa_pages():
    if current_app.config.get("API_ONLY"):
        return jsonify({"error": "Not found"}), 404
    return _render_index(_get_pwa_config())


def _render_index(pwa):
    """渲染带 PWA 配置的首页"""
    import os
    static_folder = current_app.config.get("STATIC_FOLDER", "frontend")
    html_path = os.path.join(static_folder, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        tpl = f.read()
    # 替换 PWA 相关占位符为 Jinja2 变量
    tpl = tpl.replace('content="#E8A317"', 'content="{{ theme_color }}"')
    tpl = tpl.replace('content="投资追踪"', 'content="{{ short_name }}"')
    tpl = tpl.replace(">投资追踪器</title>", ">{{ name }}</title>")
    tpl = tpl.replace('<link rel="apple-touch-icon" href="/frontend/icons/icon-192.png">', '<link rel="apple-touch-icon" href="{{ icon_192 }}">')
    tpl = tpl.replace('<link rel="icon" type="image/png" sizes="192x192" href="/frontend/icons/icon-192.png">', '<link rel="icon" type="image/png" sizes="192x192" href="{{ favicon_href }}">')
    icon_192 = pwa.get("icon_192", "/frontend/icons/icon-192.png")
    favicon_href = (pwa.get("favicon") or "").strip() or icon_192
    from jinja2 import Template
    return Template(tpl).render(
        name=pwa.get("name", "投资追踪器"),
        short_name=pwa.get("short_name", "投资追踪"),
        theme_color=pwa.get("theme_color", "#E8A317"),
        icon_192=icon_192,
        favicon_href=favicon_href,
    )


@main_bp.route("/manifest.json")
def serve_manifest():
    """PWA manifest，动态从配置生成"""
    if current_app.config.get("API_ONLY"):
        return jsonify({"error": "Not found"}), 404
    pwa = _get_pwa_config()
    manifest = {
        "name": pwa.get("name", "投资追踪器"),
        "short_name": pwa.get("short_name", "投资追踪"),
        "description": pwa.get("description", "投资组合追踪与收益分析工具"),
        "start_url": "/",
        "display": pwa.get("display", "standalone"),
        "background_color": pwa.get("background_color", "#ffffff"),
        "theme_color": pwa.get("theme_color", "#E8A317"),
        "orientation": "portrait-primary",
        "icons": [
            {"src": pwa.get("icon_192", "/frontend/icons/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": pwa.get("icon_512", "/frontend/icons/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": pwa.get("icon_512", "/frontend/icons/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    resp = jsonify(manifest)
    resp.headers["Content-Type"] = "application/manifest+json"
    return resp


@main_bp.route("/sw.js")
def serve_sw():
    """PWA Service Worker，根路径便于控制全站"""
    if current_app.config.get("API_ONLY"):
        return jsonify({"error": "Not found"}), 404
    static_folder = current_app.config.get("STATIC_FOLDER", "frontend")
    return send_from_directory(static_folder, "sw.js", mimetype="application/javascript")


@main_bp.route("/frontend/<path:filename>")
def serve_static(filename):
    if current_app.config.get("API_ONLY"):
        return jsonify({"error": "Not found"}), 404
    static_folder = current_app.config.get("STATIC_FOLDER", "frontend")
    return send_from_directory(static_folder, filename)


@main_bp.route("/plugins/<plugin_id>/<path:filename>")
def serve_plugin_static(plugin_id, filename):
    """提供插件目录下的静态文件（如 css、js），仅允许在插件目录内"""
    import os
    if current_app.config.get("API_ONLY"):
        return jsonify({"error": "Not found"}), 404
    static_folder = current_app.config.get("STATIC_FOLDER", "frontend")
    base_dir = os.path.dirname(os.path.abspath(static_folder))
    plugin_dir = os.path.join(base_dir, "plugins", plugin_id)
    if ".." in filename or ".." in plugin_id:
        return jsonify({"error": "非法路径"}), 400
    real_plugin = os.path.realpath(plugin_dir)
    real_base = os.path.realpath(base_dir)
    if not real_plugin.startswith(real_base + os.sep) or not os.path.isdir(real_plugin):
        return jsonify({"error": "未找到"}), 404
    file_path = os.path.join(plugin_dir, filename)
    real_file = os.path.realpath(file_path)
    if not real_file.startswith(real_plugin + os.sep) and real_file != real_plugin:
        return jsonify({"error": "未找到"}), 404
    if not os.path.isfile(real_file):
        return jsonify({"error": "未找到"}), 404
    return send_from_directory(plugin_dir, filename)


@main_bp.route("/api/avatars/<path:filename>")
def serve_avatar(filename):
    """提供用户头像静态文件"""
    import os
    uploads = current_app.config.get("UPLOADS_FOLDER")
    if not uploads:
        return jsonify({"error": "未配置"}), 404
    avatars_dir = os.path.join(uploads, "avatars")
    # 仅允许文件名，防止路径遍历
    if ".." in filename or "/" in filename or "\\" in filename:
        return jsonify({"error": "非法路径"}), 400
    path = os.path.join(avatars_dir, filename)
    real_path = os.path.realpath(path)
    real_avatars = os.path.realpath(avatars_dir)
    if not real_path.startswith(real_avatars + os.sep) or not os.path.isfile(real_path):
        return jsonify({"error": "未找到"}), 404
    return send_from_directory(avatars_dir, filename)
