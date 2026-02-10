"""
默认币种与汇率设置 - 多数据库共用
从本模块读取默认汇率，可选由 conf/config.yaml 的 default_exchange_rates 覆盖，保证 SQLite/PostgreSQL/D1 行为一致。
"""

import os
from typing import Dict, Tuple, List, Optional

# 内置默认汇率（相对人民币），所有数据库初始化与「确保币种存在」时统一使用
DEFAULT_EXCHANGE_RATES: Dict[str, float] = {
    "CNY": 1.0,
    "HKD": 0.92,
    "USD": 7.25,
    "EUR": 7.85,
    "GBP": 9.15,
    "JPY": 0.048,
}

# 内置币种展示信息 (名称, 符号)
CURRENCY_INFO: Dict[str, Tuple[str, str]] = {
    "CNY": ("人民币", "¥"),
    "HKD": ("港币", "HK$"),
    "USD": ("美元", "$"),
    "EUR": ("欧元", "€"),
    "GBP": ("英镑", "£"),
    "JPY": ("日元", "¥"),
}


def _load_config_rates(config_path: Optional[str] = None) -> Dict[str, float]:
    """从 config.yaml 的 default_exchange_rates 读取覆盖汇率（可选）。"""
    if not config_path or not os.path.exists(config_path):
        return {}
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        rates = (cfg.get("default_exchange_rates") or cfg.get("default_currencies"))
        if isinstance(rates, dict):
            return {str(k).upper(): float(v) for k, v in rates.items()}
    except Exception:
        pass
    return {}


def get_default_exchange_rates(config_path: Optional[str] = None) -> Dict[str, float]:
    """返回默认汇率：内置 + 配置文件覆盖。"""
    rates = dict(DEFAULT_EXCHANGE_RATES)
    rates.update(_load_config_rates(config_path))
    return rates


def get_currency_info(code: str, config_path: Optional[str] = None) -> Tuple[str, str, float]:
    """
    返回 (name, symbol, exchange_rate)。
    名称与符号优先用内置 CURRENCY_INFO，汇率用 get_default_exchange_rates（含配置覆盖）。
    若 code 不在内置中，则 name/symbol 用 code，汇率用配置或 1.0。
    """
    code_upper = (code or "CNY").strip().upper() or "CNY"
    rates = get_default_exchange_rates(config_path)
    rate = rates.get(code_upper, 1.0)
    name, symbol = CURRENCY_INFO.get(code_upper, (code_upper, code_upper))
    return (name, symbol, rate)


def get_all_default_currencies(config_path: Optional[str] = None) -> List[Tuple[str, str, str, float]]:
    """返回 [(code, name, symbol, exchange_rate), ...]，用于初始化表。"""
    rates = get_default_exchange_rates(config_path)
    result = []
    for code, rate in rates.items():
        name, symbol = CURRENCY_INFO.get(code, (code, code))
        result.append((code, name, symbol, rate))
    return result
