"""
参考数据蓝图 - 分类、币种
"""

import logging
from flask import Blueprint

from app.extensions import get_db
from app.utils import api_error, api_success

logger = logging.getLogger(__name__)

reference_bp = Blueprint("reference", __name__, url_prefix="/api")


@reference_bp.route("/categories", methods=["GET"])
def get_categories():
    try:
        database = get_db()
        categories = database.get_categories()
        categories_list = categories.to_dict(orient="records") if not categories.empty else []
        return api_success(data={"categories": categories_list})
    except Exception as e:
        logger.error(f"Get categories error: {e}")
        return api_error(str(e), 500)


@reference_bp.route("/currencies", methods=["GET"])
def get_currencies():
    try:
        database = get_db()
        currencies = database.get_currencies()
        currencies_list = currencies.to_dict(orient="records") if not currencies.empty else []
        return api_success(data={"currencies": currencies_list})
    except Exception as e:
        logger.error(f"Get currencies error: {e}")
        return api_error(str(e), 500)
