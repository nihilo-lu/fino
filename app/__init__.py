"""
应用工厂 - 工厂模式创建 Flask 应用
支持多环境配置、蓝图注册、扩展初始化
"""

import os
import logging
from flask import Flask
from flask_cors import CORS

from app.config import get_config_path
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

    app = Flask(
        __name__,
        static_folder=static_folder,
        static_url_path="/frontend",
    )

    # 1. 加载配置
    app.config["CONFIG_PATH"] = config_path
    app.config["STATIC_FOLDER"] = static_folder

    # 2. 初始化扩展
    CORS(app)

    # 3. 注册蓝图
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

    # 4. 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    return app
