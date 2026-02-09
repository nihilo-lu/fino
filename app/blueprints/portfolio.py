"""
组合蓝图 - 持仓、组合统计
"""

import logging
from flask import Blueprint, request

from app.extensions import get_db
from app.utils import cors_jsonify

logger = logging.getLogger(__name__)

portfolio_bp = Blueprint("portfolio", __name__, url_prefix="/api")


@portfolio_bp.route("/portfolio/stats", methods=["GET"])
def get_portfolio_stats():
    ledger_id = request.args.get("ledger_id", type=int)
    account_id = request.args.get("account_id", type=int)

    try:
        database = get_db()
        stats = database.get_portfolio_stats(ledger_id, account_id)
        return cors_jsonify({"stats": stats})
    except Exception as e:
        logger.error(f"Get portfolio stats error: {e}")
        return cors_jsonify({"error": str(e)}, 500)


@portfolio_bp.route("/positions", methods=["GET"])
def get_positions():
    ledger_id = request.args.get("ledger_id", type=int)
    account_id = request.args.get("account_id", type=int)

    try:
        database = get_db()
        positions = database.get_positions(ledger_id, account_id)
        positions_list = positions.to_dict(orient="records") if not positions.empty else []
        return cors_jsonify({"positions": positions_list})
    except Exception as e:
        logger.error(f"Get positions error: {e}")
        return cors_jsonify({"error": str(e)}, 500)


@portfolio_bp.route("/positions/<int:position_id>", methods=["DELETE"])
def delete_position(position_id):
    try:
        database = get_db()
        cursor = database.conn.cursor()
        cursor.execute("DELETE FROM positions WHERE id = ?", (position_id,))
        database.conn.commit()
        return cors_jsonify({"success": True, "message": "删除成功"})
    except Exception as e:
        logger.error(f"Delete position error: {e}")
        return cors_jsonify({"error": str(e)}, 500)
