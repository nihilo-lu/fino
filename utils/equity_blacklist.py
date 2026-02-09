"""
权益类账户黑名单

用于净值法收益率计算：当日净资产只汇总非权益类账户，排除黑名单中的权益类账户。
黑名单为账户名称包含的关键词，命中则视为权益类，不参与净资产汇总。

配置覆盖（可选）：在 conf/main_config.ini 中添加：
    [equity]
    account_name_blacklist = 投资本金, 权益, Capital
"""

from typing import List

# 默认权益类账户名称关键词（黑名单），账户名称包含任一关键词即排除
DEFAULT_EQUITY_BLACKLIST: List[str] = [
    "投资本金",
    "权益",
]


def get_equity_blacklist() -> List[str]:
    """
    获取权益类账户黑名单关键词列表。
    可从配置文件覆盖，默认使用 DEFAULT_EQUITY_BLACKLIST。
    """
    try:
        from utils.config_loader import get_config
        config = get_config()
        blacklist = config.getlist("equity", "account_name_blacklist", fallback=None)
        if blacklist:
            return blacklist
    except Exception:
        pass
    return DEFAULT_EQUITY_BLACKLIST.copy()


def build_account_exclusion_sql(column: str = "name") -> str:
    """
    构建 SQL 排除条件：账户名称不包含黑名单中任一关键词。

    Args:
        column: 账户名称所在列，如 "a.name" 或 "accounts.name"

    Returns:
        形如 "AND (name NOT LIKE '%投资本金%' AND name NOT LIKE '%权益%')" 的字符串
    """
    blacklist = get_equity_blacklist()
    if not blacklist:
        return ""
    conditions = " AND ".join(
        f"{column} NOT LIKE '%{kw}%'" for kw in blacklist
    )
    return f"AND ({conditions})"


def is_equity_account(account_name: str) -> bool:
    """
    判断账户是否为权益类（应排除）。

    Args:
        account_name: 账户名称

    Returns:
        True 表示权益类应排除，False 表示资产类应纳入
    """
    if not account_name:
        return False
    blacklist = get_equity_blacklist()
    name_lower = account_name.lower()
    for kw in blacklist:
        if kw.lower() in name_lower:
            return True
    return False
