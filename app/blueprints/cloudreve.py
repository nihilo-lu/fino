"""
Cloudreve 网盘蓝图 - 与 Cloudreve 集成，支持文件管理、上传
API 文档: https://cloudrevev4.apifox.cn/
"""

import re
import logging
import requests
from flask import Blueprint, request, session, current_app

from app.utils import api_error, api_success
from utils.db_base import get_db_manager
from utils.db_config import get_database_config

logger = logging.getLogger(__name__)

cloudreve_bp = Blueprint("cloudreve", __name__, url_prefix="/api/cloudreve")


def _get_username():
    """从 session 获取当前用户"""
    return session.get("username")


def _cloudreve_enabled():
    """检查 Cloudreve 功能是否在配置中开启（支持 lab.cloudreve 与旧版 cloudreve）"""
    try:
        from utils.auth_config import load_config
        cfg = load_config(current_app.config.get("CONFIG_PATH")) or {}
        cr = cfg.get("lab", {}).get("cloudreve") or cfg.get("cloudreve") or {}
        return bool(cr.get("enabled", False))
    except Exception:
        return False


def _normalize_url(url: str) -> str:
    """标准化 Cloudreve 服务器 URL，确保以 /api/v4 结尾"""
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    # 移除已有的 /api/v4 或 /api 后缀，统一添加
    url = re.sub(r"/api/v4/?$", "", url)
    url = re.sub(r"/api/?$", "", url)
    return url.rstrip("/") + "/api/v4"


def _get_binding(username: str):
    """获取用户的 Cloudreve 绑定信息"""
    cfg = get_database_config(current_app.config.get("CONFIG_PATH"))
    dbm = get_db_manager(
        db_type=cfg["type"],
        db_path=cfg["sqlite"]["path"],
        pg_host=cfg["postgresql"]["host"],
        pg_port=cfg["postgresql"]["port"],
        pg_database=cfg["postgresql"]["database"],
        pg_user=cfg["postgresql"]["user"],
        pg_password=cfg["postgresql"]["password"],
        pg_sslmode=cfg["postgresql"]["sslmode"],
        d1_account_id=cfg["d1"]["account_id"],
        d1_database_id=cfg["d1"]["database_id"],
        d1_api_token=cfg["d1"]["api_token"],
    )
    conn = dbm.get_connection()
    cursor = conn.cursor()
    if cfg["type"] == "postgresql":
        cursor.execute(
            "SELECT cloudreve_url, access_token, refresh_token FROM cloudreve_bindings WHERE username = %s",
            (username,),
        )
    else:
        cursor.execute(
            "SELECT cloudreve_url, access_token, refresh_token FROM cloudreve_bindings WHERE username = ?",
            (username,),
        )
    row = cursor.fetchone()
    dbm.close()
    if not row:
        return None
    return {
        "cloudreve_url": row[0],
        "access_token": row[1],
        "refresh_token": row[2],
    }


def _save_binding(username: str, cloudreve_url: str, access_token: str, refresh_token: str = None):
    """保存或更新 Cloudreve 绑定"""
    cfg = get_database_config(current_app.config.get("CONFIG_PATH"))
    dbm = get_db_manager(
        db_type=cfg["type"],
        db_path=cfg["sqlite"]["path"],
        pg_host=cfg["postgresql"]["host"],
        pg_port=cfg["postgresql"]["port"],
        pg_database=cfg["postgresql"]["database"],
        pg_user=cfg["postgresql"]["user"],
        pg_password=cfg["postgresql"]["password"],
        pg_sslmode=cfg["postgresql"]["sslmode"],
        d1_account_id=cfg["d1"]["account_id"],
        d1_database_id=cfg["d1"]["database_id"],
        d1_api_token=cfg["d1"]["api_token"],
    )
    conn = dbm.get_connection()
    cursor = conn.cursor()
    if cfg["type"] == "postgresql":
        cursor.execute(
            """
            INSERT INTO cloudreve_bindings (username, cloudreve_url, access_token, refresh_token, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (username) DO UPDATE SET
                cloudreve_url = EXCLUDED.cloudreve_url,
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                updated_at = CURRENT_TIMESTAMP
            """,
            (username, cloudreve_url, access_token, refresh_token or ""),
        )
    else:
        cursor.execute(
            """
            INSERT INTO cloudreve_bindings (username, cloudreve_url, access_token, refresh_token, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(username) DO UPDATE SET
                cloudreve_url = excluded.cloudreve_url,
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                updated_at = CURRENT_TIMESTAMP
            """,
            (username, cloudreve_url, access_token, refresh_token or ""),
        )
    conn.commit()
    dbm.close()


def _delete_binding(username: str):
    """删除 Cloudreve 绑定"""
    cfg = get_database_config(current_app.config.get("CONFIG_PATH"))
    dbm = get_db_manager(
        db_type=cfg["type"],
        db_path=cfg["sqlite"]["path"],
        pg_host=cfg["postgresql"]["host"],
        pg_port=cfg["postgresql"]["port"],
        pg_database=cfg["postgresql"]["database"],
        pg_user=cfg["postgresql"]["user"],
        pg_password=cfg["postgresql"]["password"],
        pg_sslmode=cfg["postgresql"]["sslmode"],
        d1_account_id=cfg["d1"]["account_id"],
        d1_database_id=cfg["d1"]["database_id"],
        d1_api_token=cfg["d1"]["api_token"],
    )
    conn = dbm.get_connection()
    cursor = conn.cursor()
    if cfg["type"] == "postgresql":
        cursor.execute("DELETE FROM cloudreve_bindings WHERE username = %s", (username,))
    else:
        cursor.execute("DELETE FROM cloudreve_bindings WHERE username = ?", (username,))
    conn.commit()
    dbm.close()


def _cloudreve_request(method: str, base_url: str, path: str, token: str = None, **kwargs):
    """向 Cloudreve API 发送请求"""
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    kwargs.setdefault("timeout", 10)
    # 支持自签名证书：lab.cloudreve.verify_ssl: false
    try:
        from utils.auth_config import load_config
        cfg = load_config(current_app.config.get("CONFIG_PATH")) or {}
        cr = cfg.get("lab", {}).get("cloudreve") or cfg.get("cloudreve") or {}
        if cr.get("verify_ssl", True) is False:
            kwargs["verify"] = False
    except Exception:
        pass
    try:
        resp = requests.request(method, url, headers=headers, **kwargs)
        return resp
    except requests.exceptions.Timeout:
        logger.error("Cloudreve request timeout: %s", url)
        raise
    except requests.exceptions.SSLError as e:
        logger.error(f"Cloudreve SSL error: {e}")
        raise ValueError("SSL 证书验证失败，若使用自签名证书请确认服务器地址正确")
    except requests.RequestException as e:
        logger.error(f"Cloudreve request error: {e}")
        raise


def _require_admin():
    """确保当前用户为管理员"""
    username = _get_username()
    if not username:
        return None, "未登录"
    try:
        from utils.auth_config import load_config, is_admin
        cfg = load_config(current_app.config.get("CONFIG_PATH"))
        user = (cfg.get("credentials", {}).get("usernames") or {}).get(username)
        if not user or not is_admin(user.get("roles")):
            return None, "需要管理员权限"
        return username, None
    except Exception as e:
        return None, str(e)


@cloudreve_bp.route("/config", methods=["GET"])
def get_config():
    """获取 Cloudreve 功能配置（是否开启）"""
    username = _get_username()
    if not username:
        return api_error("未登录", 401)
    enabled = _cloudreve_enabled()
    return api_success(data={"enabled": enabled})


@cloudreve_bp.route("/config", methods=["PUT"])
def save_config():
    """保存 Cloudreve 功能配置（仅管理员）"""
    _, err = _require_admin()
    if err:
        return api_error(err, 403)
    from utils.auth_config import load_config, save_config as _save_config
    data = request.get_json() or {}
    enabled = bool(data.get("enabled", False))
    try:
        cfg = load_config(current_app.config.get("CONFIG_PATH"))
        if not cfg:
            return api_error("无法读取配置文件，请确认 conf/config.yaml 存在", 500)
        if "lab" not in cfg:
            cfg["lab"] = {}
        if "cloudreve" not in cfg["lab"]:
            cfg["lab"]["cloudreve"] = {}
        cfg["lab"]["cloudreve"]["enabled"] = enabled
        if not _save_config(current_app.config.get("CONFIG_PATH"), cfg):
            return api_error("保存配置失败", 500)
        return api_success(message="已保存")
    except Exception as e:
        logger.error(f"Save cloudreve config error: {e}")
        return api_error(str(e), 500)


@cloudreve_bp.route("/status", methods=["GET"])
def get_status():
    """获取当前用户的 Cloudreve 绑定状态"""
    username = _get_username()
    if not username:
        return api_error("未登录", 401)
    if not _cloudreve_enabled():
        return api_success(data={"bound": False, "cloudreve_url": None})
    binding = _get_binding(username)
    if not binding:
        return api_success(data={"bound": False, "cloudreve_url": None})
    # 不返回 token，只返回绑定状态和 URL
    return api_success(data={
        "bound": True,
        "cloudreve_url": binding["cloudreve_url"].replace("/api/v4", ""),
    })


@cloudreve_bp.route("/verify", methods=["GET"])
def verify_server():
    """验证 Cloudreve 服务器连通性（Ping）"""
    username = _get_username()
    if not username:
        return api_error("未登录", 401)
    if not _cloudreve_enabled():
        return api_error("网盘功能未开启", 403)
    url = (request.args.get("url") or "").strip()
    if not url:
        return api_error("请提供服务器地址", 400)
    base_url = _normalize_url(url)
    try:
        resp = _cloudreve_request("GET", base_url, "site/ping")
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code == 200 and data.get("code") == 0:
            return api_success(data={
                "valid": True,
                "version": data.get("data", ""),
                "login_url": base_url.replace("/api/v4", "") + "/",
            })
        return api_error("无法连接该服务器", 400)
    except ValueError as e:
        return api_error(str(e), 400)
    except Exception as e:
        logger.error(f"Cloudreve ping error: {e}")
        return api_error(f"验证失败: {str(e)}", 500)


@cloudreve_bp.route("/captcha", methods=["GET"])
def get_captcha():
    """获取 Cloudreve 验证码（代理请求）"""
    username = _get_username()
    if not username:
        return api_error("未登录", 401)
    if not _cloudreve_enabled():
        return api_error("网盘功能未开启", 403)
    url = (request.args.get("url") or "").strip()
    if not url:
        return api_error("请提供服务器地址", 400)
    base_url = _normalize_url(url)
    try:
        resp = _cloudreve_request("GET", base_url, "site/captcha")
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code == 200 and data.get("code") == 0:
            return api_success(data=data.get("data", {}))
        return api_error("获取验证码失败", 400)
    except Exception as e:
        logger.error(f"Cloudreve captcha error: {e}")
        return api_error(f"获取验证码失败: {str(e)}", 500)


@cloudreve_bp.route("/bind", methods=["POST"])
def bind_account():
    """绑定 Cloudreve 账号（密码登录）"""
    username = _get_username()
    if not username:
        return api_error("未登录", 401)
    if not _cloudreve_enabled():
        return api_error("网盘功能未开启", 403)
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password", "")
    captcha = (data.get("captcha") or "").strip()
    ticket = (data.get("ticket") or "").strip()
    if not url or not email or not password:
        return api_error("请填写服务器地址、邮箱和密码", 400)
    base_url = _normalize_url(url)
    try:
        resp = _cloudreve_request(
            "POST",
            base_url,
            "session/token",
            json={
                "email": email,
                "password": password,
                "captcha": captcha,
                "ticket": ticket,
            },
            headers={"Content-Type": "application/json"},
        )
        result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code != 200:
            return api_error(result.get("msg", "登录失败"), 400)
        code = result.get("code", 0)
        if code != 0:
            # 40026=验证码错误, 40027=需要刷新验证码
            if code in (40026, 40027):
                return api_error("需要验证码，请先获取并填写验证码", 400)
            return api_error(result.get("msg", "登录失败"), 400)
        token_data = result.get("data", {}).get("token", {})
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        if not access_token:
            return api_error("登录成功但未获取到令牌", 500)
        _save_binding(username, base_url, access_token, refresh_token)
        return api_success(message="绑定成功")
    except Exception as e:
        logger.error(f"Cloudreve bind error: {e}")
        return api_error(f"绑定失败: {str(e)}", 500)


@cloudreve_bp.route("/unbind", methods=["POST"])
def unbind_account():
    """解绑 Cloudreve"""
    username = _get_username()
    if not username:
        return api_error("未登录", 401)
    _delete_binding(username)
    return api_success(message="已解绑")


@cloudreve_bp.route("/files", methods=["GET"])
def list_files():
    """列出 Cloudreve 文件"""
    username = _get_username()
    if not username:
        return api_error("未登录", 401)
    if not _cloudreve_enabled():
        return api_error("网盘功能未开启", 403)
    binding = _get_binding(username)
    if not binding:
        return api_error("请先在设置中绑定 Cloudreve", 400)
    uri = request.args.get("uri", "cloudreve://my/")
    page = request.args.get("page", 0, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    try:
        resp = _cloudreve_request(
            "GET",
            binding["cloudreve_url"],
            "file",
            token=binding["access_token"],
            params={"uri": uri, "page": page, "page_size": page_size},
        )
        result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code == 401:
            return api_error("登录已过期，请重新绑定", 401)
        if resp.status_code != 200 or result.get("code") != 0:
            return api_error(result.get("msg", "获取文件列表失败"), 400)
        cloudreve_data = result.get("data", {})
        # Cloudreve 返回 objects 而非 files，统一为 files
        if "objects" in cloudreve_data and "files" not in cloudreve_data:
            cloudreve_data = {**cloudreve_data, "files": cloudreve_data["objects"]}
        return api_success(data=cloudreve_data)
    except Exception as e:
        logger.error(f"Cloudreve list files error: {e}")
        return api_error(f"获取文件列表失败: {str(e)}", 500)


@cloudreve_bp.route("/download-url", methods=["POST"])
def create_download_url():
    """创建下载链接"""
    username = _get_username()
    if not username:
        return api_error("未登录", 401)
    if not _cloudreve_enabled():
        return api_error("网盘功能未开启", 403)
    binding = _get_binding(username)
    if not binding:
        return api_error("请先在设置中绑定 Cloudreve", 400)
    data = request.get_json() or {}
    uri = data.get("uri")
    if not uri:
        return api_error("请提供文件 URI", 400)
    try:
        resp = _cloudreve_request(
            "POST",
            binding["cloudreve_url"],
            "file/url",
            token=binding["access_token"],
            json={"uris": [uri]},
            headers={"Content-Type": "application/json"},
        )
        result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code == 401:
            return api_error("登录已过期，请重新绑定", 401)
        if resp.status_code != 200 or result.get("code") != 0:
            return api_error(result.get("msg", "创建下载链接失败"), 400)
        return api_success(data=result.get("data", {}))
    except Exception as e:
        logger.error(f"Cloudreve download url error: {e}")
        return api_error(f"创建下载链接失败: {str(e)}", 500)


@cloudreve_bp.route("/upload", methods=["POST"])
def upload_file():
    """上传文件到 Cloudreve（使用 Update file content: PUT /file/content）"""
    username = _get_username()
    if not username:
        return api_error("未登录", 401)
    if not _cloudreve_enabled():
        return api_error("网盘功能未开启", 403)
    binding = _get_binding(username)
    if not binding:
        return api_error("请先在设置中绑定 Cloudreve", 400)
    if "file" not in request.files:
        return api_error("未选择文件", 400)
    file = request.files["file"]
    if not file or not file.filename:
        return api_error("未选择文件", 400)
    target_uri = (request.form.get("uri") or "cloudreve://my/").strip()
    if not target_uri.endswith("/"):
        target_uri += "/"
    target_uri += file.filename
    try:
        # Cloudreve Update file content: PUT /file/content?uri=...
        file_content = file.read()
        resp = _cloudreve_request(
            "PUT",
            binding["cloudreve_url"],
            "file/content",
            token=binding["access_token"],
            params={"uri": target_uri},
            data=file_content,
            headers={"Content-Type": file.content_type or "application/octet-stream"},
        )
        result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code == 401:
            return api_error("登录已过期，请重新绑定", 401)
        if resp.status_code not in (200, 201) or result.get("code") != 0:
            return api_error(result.get("msg", "上传失败"), 400)
        return api_success(data=result.get("data", {}), message="上传成功")
    except Exception as e:
        logger.error(f"Cloudreve upload error: {e}")
        return api_error(f"上传失败: {str(e)}", 500)


@cloudreve_bp.route("/delete", methods=["POST"])
def delete_file():
    """删除 Cloudreve 文件"""
    username = _get_username()
    if not username:
        return api_error("未登录", 401)
    if not _cloudreve_enabled():
        return api_error("网盘功能未开启", 403)
    binding = _get_binding(username)
    if not binding:
        return api_error("请先在设置中绑定 Cloudreve", 400)
    data = request.get_json() or {}
    uri = data.get("uri")
    if not uri:
        return api_error("请提供文件 URI", 400)
    try:
        resp = _cloudreve_request(
            "DELETE",
            binding["cloudreve_url"],
            "file",
            token=binding["access_token"],
            json={"uris": [uri]},
            headers={"Content-Type": "application/json"},
        )
        result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code == 401:
            return api_error("登录已过期，请重新绑定", 401)
        if resp.status_code != 200 or result.get("code") != 0:
            return api_error(result.get("msg", "删除失败"), 400)
        return api_success(message="已删除")
    except Exception as e:
        logger.error(f"Cloudreve delete error: {e}")
        return api_error(f"删除失败: {str(e)}", 500)


@cloudreve_bp.route("/mkdir", methods=["POST"])
def create_folder():
    """创建文件夹"""
    username = _get_username()
    if not username:
        return api_error("未登录", 401)
    if not _cloudreve_enabled():
        return api_error("网盘功能未开启", 403)
    binding = _get_binding(username)
    if not binding:
        return api_error("请先在设置中绑定 Cloudreve", 400)
    data = request.get_json() or {}
    parent_uri = (data.get("parent_uri") or "cloudreve://my/").strip()
    name = (data.get("name") or "").strip()
    if not name:
        return api_error("请输入文件夹名称", 400)
    if not parent_uri.endswith("/"):
        parent_uri += "/"
    target_uri = parent_uri + name
    try:
        resp = _cloudreve_request(
            "POST",
            binding["cloudreve_url"],
            "file/create",
            token=binding["access_token"],
            json={"type": "directory", "uri": target_uri},
            headers={"Content-Type": "application/json"},
        )
        result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code == 401:
            return api_error("登录已过期，请重新绑定", 401)
        if resp.status_code not in (200, 201) or result.get("code") != 0:
            return api_error(result.get("msg", "创建文件夹失败"), 400)
        return api_success(data=result.get("data", {}), message="创建成功")
    except Exception as e:
        logger.error(f"Cloudreve mkdir error: {e}")
        return api_error(f"创建文件夹失败: {str(e)}", 500)
