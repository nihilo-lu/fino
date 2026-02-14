"""
分析蓝图 - 收益率等分析接口
"""

import logging
from flask import Blueprint, request

from app.extensions import get_db
from app.utils import api_error, api_success

logger = logging.getLogger(__name__)

analysis_bp = Blueprint("analysis", __name__, url_prefix="/api/analysis")


@analysis_bp.route("/returns", methods=["GET"])
def get_returns_analysis():
    ledger_id = request.args.get("ledger_id", type=int)
    account_id = request.args.get("account_id", type=int)

    try:
        database = get_db()
        return_rate = database.get_latest_cumulative_return(ledger_id)
        portfolio_stats = database.get_portfolio_stats(ledger_id, account_id)
        realized_pl = database.get_realized_pl(ledger_id, account_id)

        # 净值明细（用于完整净值明细表）
        nav_details = []
        df = database.get_return_rate(ledger_id=ledger_id)
        if not df.empty:
            drop_cols = ["id", "ledger_id", "created_at", "updated_at"]
            df = df.drop(columns=[c for c in drop_cols if c in df.columns])
            df["date"] = df["date"].astype(str)
            nav_details = df.to_dict(orient="records")

        return api_success(data={
            "cumulative_return": return_rate,
            "portfolio_stats": portfolio_stats,
            "realized_pl": realized_pl,
            "nav_details": nav_details,
        })
    except Exception as e:
        logger.error(f"Get returns analysis error: {e}")
        return api_error(str(e), 500)
