"""
插件中心 API - 插件的安装、卸载、启用、禁用与注册表查询
"""

import logging
from flask import Blueprint, request, current_app

from app.utils import api_error, api_success

logger = logging.getLogger(__name__)

plugins_bp = Blueprint("plugins", __name__, url_prefix="/api/plugins")


def _get_manager():
    """获取插件管理器"""
    return getattr(current_app, "plugin_manager", None)


def _get_registry():
    """获取插件注册表"""
    return getattr(current_app, "plugin_registry", None)


def _require_admin():
    """检查管理员权限"""
    from flask import session
    from utils.auth_config import load_config, is_admin, get_user
    if not session.get("username"):
        return False, "未登录"
    cfg = load_config(current_app.config.get("CONFIG_PATH"))
    user = get_user(cfg or {}, session["username"])
    if not is_admin(user.get("roles")):
        return False, "仅管理员可操作"
    return True, None


# ========== 插件中心（注册表） ==========


@plugins_bp.route("/registry", methods=["GET"])
def get_registry():
    """获取插件中心列表（所有可安装的插件）"""
    reg = _get_registry()
    if not reg:
        return api_error("插件中心未初始化", 500)
    plugins = reg.fetch_registry()
    return api_success(data={"plugins": plugins})


@plugins_bp.route("/registry/<plugin_id>", methods=["GET"])
def get_plugin_info(plugin_id):
    """获取单个插件详情"""
    reg = _get_registry()
    if not reg:
        return api_error("插件中心未初始化", 500)
    info = reg.get_plugin_info(plugin_id)
    if not info:
        return api_error("插件不存在", 404)
    return api_success(data=info)


# ========== 已安装插件管理 ==========


@plugins_bp.route("/installed", methods=["GET"])
def list_installed():
    """获取已安装插件列表及状态"""
    mgr = _get_manager()
    if not mgr:
        return api_error("插件管理器未初始化", 500)
    state = mgr.get_plugin_state()
    return api_success(data=state)


@plugins_bp.route("/installed/<plugin_id>/enable", methods=["POST"])
def enable_plugin(plugin_id):
    """启用插件"""
    ok, err = _require_admin()
    if not ok:
        return api_error(err, 401 if "未登录" in err else 403)
    mgr = _get_manager()
    if not mgr:
        return api_error("插件管理器未初始化", 500)
    if mgr.enable_plugin(plugin_id):
        return api_success(message="已启用")
    return api_error("启用失败，请检查插件是否已安装", 400)


@plugins_bp.route("/installed/<plugin_id>/disable", methods=["POST"])
def disable_plugin(plugin_id):
    """禁用插件"""
    ok, err = _require_admin()
    if not ok:
        return api_error(err, 401 if "未登录" in err else 403)
    mgr = _get_manager()
    if not mgr:
        return api_error("插件管理器未初始化", 500)
    if mgr.disable_plugin(plugin_id):
        return api_success(message="已禁用")
    return api_error("禁用失败", 400)


@plugins_bp.route("/installed/<plugin_id>/uninstall", methods=["POST"])
def uninstall_plugin(plugin_id):
    """卸载插件（删除插件目录，需重启生效）"""
    ok, err = _require_admin()
    if not ok:
        return api_error(err, 401 if "未登录" in err else 403)
    mgr = _get_manager()
    if not mgr:
        return api_error("插件管理器未初始化", 500)
    if mgr.uninstall_plugin(plugin_id):
        return api_success(message="已卸载，请重启应用生效")
    return api_error("卸载失败", 400)


@plugins_bp.route("/install/<plugin_id>", methods=["POST"])
def install_plugin(plugin_id):
    """安装内置插件（fino-ai-chat, fino-cloudreve）"""
    ok, err = _require_admin()
    if not ok:
        return api_error(err, 401 if "未登录" in err else 403)
    mgr = _get_manager()
    if not mgr:
        return api_error("插件管理器未初始化", 500)
    if mgr.install_builtin(plugin_id):
        return api_success(message="已安装，请重启应用生效")
    return api_error("安装失败或插件不存在", 400)


@plugins_bp.route("/frontend-manifest", methods=["GET"])
def get_frontend_manifest():
    """
    获取前端所需的插件清单（导航项、设置 Tab、悬浮组件等）
    供前端动态渲染侧边栏、设置页等
    """
    mgr = _get_manager()
    if not mgr:
        return api_success(data={"nav_items": [], "settings_tabs": [], "floating_widgets": []})
    manifests = mgr.get_registered_manifests()
    nav_items = []
    settings_tabs = []
    floating_widgets = []
    for m in manifests:
        if m.get("nav_item"):
            nav_items.append({**m["nav_item"], "plugin_id": m["id"]})
        if m.get("settings_tab"):
            settings_tabs.append({**m["settings_tab"], "plugin_id": m["id"]})
        if m.get("floating_widget"):
            floating_widgets.append({**m["floating_widget"], "plugin_id": m["id"]})
    return api_success(data={
        "nav_items": nav_items,
        "settings_tabs": settings_tabs,
        "floating_widgets": floating_widgets,
    })
