"""
行情蓝图 - 股票价格、汇率
"""

import logging
from flask import Blueprint, request

from app.extensions import get_db
from app.utils import api_error, api_success

logger = logging.getLogger(__name__)

market_bp = Blueprint("market", __name__, url_prefix="/api")


@market_bp.route("/market/price", methods=["POST"])
def fetch_market_price():
    data = request.get_json()
    code = data.get("code")

    if not code:
        return api_error("股票代码为必填", 400)

    try:
        database = get_db()
        price = database.fetch_market_price(code)
        if price is not None:
            return api_success(data={"price": price})
        return api_error("无法获取价格", 500)
    except Exception as e:
        logger.error(f"Fetch market price error: {e}")
        return cors_jsonify({"error": str(e)}, 500)


@market_bp.route("/exchange-rates", methods=["GET"])
def get_exchange_rates_at_date():
    """按日期获取各币种对人民币汇率，供资金明细弹窗试算与自动平衡。"""
    date = request.args.get("date")
    if not date:
        return api_error("缺少参数 date（YYYY-MM-DD）", 400)
    try:
        database = get_db()
        rates = database.get_exchange_rates_at_date(date)
        return api_success(data={"rates": rates})
    except Exception as e:
        logger.error(f"Get exchange rates at date error: {e}")
        return api_error(str(e), 500)


@market_bp.route("/exchange-rate", methods=["POST"])
def fetch_exchange_rate():
    data = request.get_json()
    currency = data.get("currency")

    if not currency:
        return api_error("币种代码为必填", 400)

    try:
        database = get_db()
        rate = database.fetch_exchange_rate_from_market(currency)
        if rate is not None:
            return api_success(data={"rate": rate})
        return api_error("无法获取汇率", 500)
    except Exception as e:
        logger.error(f"Fetch exchange rate error: {e}")
        return cors_jsonify({"error": str(e)}, 500)
