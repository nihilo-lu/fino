"""
参考数据蓝图 - 分类、币种
"""

import logging
from flask import Blueprint

from app.extensions import get_db
from app.utils import cors_jsonify

logger = logging.getLogger(__name__)

reference_bp = Blueprint("reference", __name__, url_prefix="/api")


@reference_bp.route("/categories", methods=["GET"])
def get_categories():
    try:
        database = get_db()
        categories = database.get_categories()
        categories_list = categories.to_dict(orient="records") if not categories.empty else []
        return cors_jsonify({"categories": categories_list})
    except Exception as e:
        logger.error(f"Get categories error: {e}")
        return cors_jsonify({"error": str(e)}, 500)


@reference_bp.route("/currencies", methods=["GET"])
def get_currencies():
    try:
        database = get_db()
        currencies = database.get_currencies()
        currencies_list = currencies.to_dict(orient="records") if not currencies.empty else []
        return cors_jsonify({"currencies": currencies_list})
    except Exception as e:
        logger.error(f"Get currencies error: {e}")
        return cors_jsonify({"error": str(e)}, 500)
