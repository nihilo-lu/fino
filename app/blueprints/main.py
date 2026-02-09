"""
主蓝图 - 健康检查、首页、静态文件
"""

from datetime import datetime
from flask import Blueprint, send_from_directory, current_app

from app.utils import cors_jsonify

main_bp = Blueprint("main", __name__)


@main_bp.route("/api/health", methods=["GET"])
def health_check():
    return cors_jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


@main_bp.route("/")
def index():
    static_folder = current_app.config.get("STATIC_FOLDER", "frontend")
    return send_from_directory(static_folder, "index.html")


@main_bp.route("/frontend/<path:filename>")
def serve_static(filename):
    static_folder = current_app.config.get("STATIC_FOLDER", "frontend")
    return send_from_directory(static_folder, filename)
