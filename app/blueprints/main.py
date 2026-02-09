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


@main_bp.route("/api/pwa/config", methods=["GET"])
def get_pwa_config():
    """获取 PWA 配置（公开，供 manifest 和前端使用）"""
    return api_success(data=_get_pwa_config())


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
        allowed = {"name", "short_name", "description", "theme_color", "background_color", "display", "icon_192", "icon_512"}
        for k, v in body.items():
            if k in allowed and v is not None:
                cfg["pwa"][k] = str(v).strip() if isinstance(v, str) else v
        if not save_config(current_app.config.get("CONFIG_PATH"), cfg):
            return api_error("保存配置失败", 500)
        return api_success(data=_get_pwa_config(), message="PWA 配置已保存")
    except Exception as e:
        return api_error(str(e), 500)


@main_bp.route("/")
def index():
    return _render_index(_get_pwa_config())


# SPA 子页面路由：刷新时返回 index.html，由前端根据 URL 渲染对应页面
@main_bp.route("/dashboard")
@main_bp.route("/positions")
@main_bp.route("/transactions")
@main_bp.route("/funds")
@main_bp.route("/add-transaction")
@main_bp.route("/analysis")
@main_bp.route("/settings")
@main_bp.route("/api-docs")
def spa_pages():
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
    tpl = tpl.replace('href="/frontend/icons/icon-192.png"', 'href="{{ icon_192 }}"')
    # 使用 render_template_string 渲染
    from jinja2 import Template
    return Template(tpl).render(
        name=pwa.get("name", "投资追踪器"),
        short_name=pwa.get("short_name", "投资追踪"),
        theme_color=pwa.get("theme_color", "#E8A317"),
        icon_192=pwa.get("icon_192", "/frontend/icons/icon-192.png"),
    )


@main_bp.route("/manifest.json")
def serve_manifest():
    """PWA manifest，动态从配置生成"""
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
    static_folder = current_app.config.get("STATIC_FOLDER", "frontend")
    return send_from_directory(static_folder, "sw.js", mimetype="application/javascript")


@main_bp.route("/frontend/<path:filename>")
def serve_static(filename):
    static_folder = current_app.config.get("STATIC_FOLDER", "frontend")
    return send_from_directory(static_folder, filename)


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
