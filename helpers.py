"""
工具函数模块
"""

from typing import Union

def calculate_profit(cost: float, current_value: float) -> tuple:
    """
    计算收益和收益率

    Args:
        cost: 成本
        current_value: 当前市值

    Returns:
        tuple: (收益金额, 收益率百分比)
    """
    profit = current_value - cost
    profit_rate = (profit / cost * 100) if cost > 0 else 0
    return profit, profit_rate


def format_currency(value: Union[int, float], symbol: str = "¥") -> str:
    """
    格式化货币显示

    Args:
        value: 金额
        symbol: 货币符号

    Returns:
        str: 格式化后的货币字符串
    """
    if value >= 0:
        return f"{symbol}{value:,.2f}"
    else:
        return f"-{symbol}{abs(value):,.2f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """
    格式化百分比显示

    Args:
        value: 百分比值
        decimals: 小数位数

    Returns:
        str: 格式化后的百分比字符串
    """
    if value >= 0:
        return f"+{value:.{decimals}f}%"
    else:
        return f"{value:.{decimals}f}%"


def format_quantity(value: float) -> str:
    """
    格式化数量显示

    Args:
        value: 数量值

    Returns:
        str: 格式化后的数量字符串
    """
    if value == int(value):
        return str(int(value))
    else:
        return f"{value:.4f}".rstrip('0').rstrip('.')


def validate_transaction(transaction: dict) -> tuple:
    """
    验证交易数据

    Args:
        transaction: 交易数据字典

    Returns:
        tuple: (是否有效, 错误信息)
    """
    required_fields = ['date', 'type', 'category', 'code', 'name', 'quantity', 'price']

    for field in required_fields:
        if field not in transaction or not transaction[field]:
            return False, f"缺少必填字段: {field}"

    if transaction['quantity'] <= 0:
        return False, "数量必须大于0"

    if transaction['price'] <= 0:
        return False, "价格必须大于0"

    if transaction['type'] not in ['买入', '卖出']:
        return False, "交易类型必须是买入或卖出"

    return True, ""


def calculate_avg_cost(old_quantity: float, old_avg_cost: float,
                       new_quantity: float, new_price: float) -> float:
    """
    计算加权平均成本

    Args:
        old_quantity: 原持仓数量
        old_avg_cost: 原平均成本
        new_quantity: 新买入数量
        new_price: 新买入价格

    Returns:
        float: 新的平均成本
    """
    total_cost = old_quantity * old_avg_cost + new_quantity * new_price
    total_quantity = old_quantity + new_quantity
    return total_cost / total_quantity if total_quantity > 0 else 0
