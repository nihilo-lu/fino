"""
应用工厂 - 工厂模式创建 Flask 应用
支持多环境配置、蓝图注册、扩展初始化、插件系统
"""

__version__ = "1.0.0"

import os
import logging
from flask import Flask, request
from flask_cors import CORS

from app.config import get_config_path
from app.auth_middleware import get_token_from_request, verify_token
from app.utils import api_error
from app.blueprints.main import main_bp
from app.blueprints.auth import auth_bp
from app.blueprints.ledgers import ledgers_bp
from app.blueprints.accounts import accounts_bp
from app.blueprints.portfolio import portfolio_bp
from app.blueprints.transactions import transactions_bp
from app.blueprints.fund_transactions import fund_transactions_bp
from app.blueprints.reference import reference_bp
from app.blueprints.market import market_bp
from app.blueprints.analysis import analysis_bp
from app.blueprints.plugins_bp import plugins_bp
from app.plugins.manager import PluginManager
from app.plugins.registry import PluginRegistry


def create_app(config_path: str | None = None) -> Flask:
    """
    应用工厂函数

    Args:
        config_path: 配置文件路径，默认 conf/config.yaml

    Returns:
        配置完成的 Flask 应用实例
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = config_path or get_config_path()
    static_folder = os.path.join(base_dir, "frontend")
    uploads_folder = os.path.join(base_dir, "uploads")

    # 不注册 Flask 自带的 /frontend 静态路由，改由 main 蓝图统一提供（便于对 styles.css 做合并等优化）
    app = Flask(__name__, static_folder=None, static_url_path=None)

    # 1. 加载配置
    app.config["CONFIG_PATH"] = config_path
    app.config["STATIC_FOLDER"] = static_folder
    app.config["UPLOADS_FOLDER"] = uploads_folder
    # Session 密钥（用于 Web 登录态）
    try:
        from utils.auth_config import load_config
        cfg = load_config(config_path) or {}
        app.config["SECRET_KEY"] = cfg.get("cookie", {}).get("key", "investment_tracker_secret")
        # 前后端分离：API 独立模式（仅提供 /api/*，不提供前端与静态）
        _api_only = os.environ.get("FINO_API_ONLY", "").strip().lower() in ("1", "true", "yes")
        if not _api_only and isinstance(cfg.get("server"), dict):
            _api_only = cfg["server"].get("api_only", False)
        app.config["API_ONLY"] = bool(_api_only)
    except Exception:
        app.config["SECRET_KEY"] = "investment_tracker_secret"
        app.config["API_ONLY"] = False

    # 2. 初始化扩展
    CORS(app, supports_credentials=True)

    # 3. 认证：支持 (1) Session 登录 (2) API Token (Bearer)
    _EXEMPT_PATHS = [
        "/api/auth/login", "/api/auth/register", "/api/health",
        "/api/plugins/registry", "/api/plugins/frontend-manifest",  # 插件中心与前端清单可匿名读取
    ]

    @app.before_request
    def require_auth():
        exempt = request.path in _EXEMPT_PATHS or request.path.startswith("/api/avatars/")
        exempt = exempt or request.path.startswith("/api/plugins/registry") or request.path == "/api/plugins/frontend-manifest" or request.path == "/api/plugins/installed"
        if exempt or not request.path.startswith("/api/"):
            return None
        # 1) API Token（Bearer）
        token = get_token_from_request()
        if token:
            payload = verify_token(token)
            if payload:
                return None
        # 2) Session（Web 登录）
        from flask import session
        if session.get("username"):
            return None
        return api_error("未登录或 Token 已过期，请重新登录", 401)

    # 4. 注册蓝图
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(ledgers_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(portfolio_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(fund_transactions_bp)
    app.register_blueprint(reference_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(analysis_bp)

    # 5. 插件中心开关：未开启时跳过一切插件相关逻辑，直接注册 AI/网盘
    plugin_center_enabled = True
    try:
        from utils.auth_config import load_config
        cfg = load_config(config_path) or {}
        plugin_center_enabled = cfg.get("lab", {}).get("plugin_center_enabled", True)
    except Exception:
        pass

    if plugin_center_enabled:
        app.register_blueprint(plugins_bp)
        app.plugin_manager = PluginManager(app)
        app.plugin_registry = PluginRegistry()
        try:
            app.plugin_manager.load_and_register_all()
            logging.info("插件中心已开启，已加载 %d 个插件", len(app.plugin_manager._loaded))
        except Exception as e:
            logging.warning("插件加载失败，将回退到直接注册 AI 与网盘: %s", e)
            from app.blueprints.ai_chat import ai_bp
            from app.blueprints.cloudreve import cloudreve_bp
            app.register_blueprint(ai_bp)
            app.register_blueprint(cloudreve_bp)

        # 5.1 插件禁用检查：禁用后即时生效，请求对应路由返回 404
        # 从已安装插件动态生成路由映射
        _PLUGIN_ROUTES = {}
        try:
            installed = app.plugin_manager.discover_installed()
            for item in installed:
                manifest = item.get("manifest", {})
                # 从 manifest 获取 API 前缀
                if manifest.get("api_prefix"):
                    _PLUGIN_ROUTES[manifest["api_prefix"]] = item["id"]
        except Exception:
            pass
        # 兜底硬编码（兼容旧配置）
        if not _PLUGIN_ROUTES:
            _PLUGIN_ROUTES = {
                "/api/ai": "fino-ai-chat",
                "/api/cloudreve": "fino-cloudreve",
            }

        @app.before_request
        def check_plugin_enabled():
            if not request.path.startswith("/api/"):
                return None
            for prefix, plugin_id in _PLUGIN_ROUTES.items():
                if request.path.startswith(prefix):
                    enabled = app.plugin_manager._load_enabled_list()
                    if plugin_id not in enabled:
                        return api_error("插件已禁用", 404)
                    break
            return None
    else:
        # 插件中心关闭：所有插件禁用，不注册 AI/网盘
        app.plugin_manager = None
        app.plugin_registry = None
        logging.info("插件中心已关闭，所有插件已禁用")

    # 6. 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    return app
