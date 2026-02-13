"""
缓存工具模块
提供缓存清除等占位接口，便于 database 等模块在数据变更后调用。
当前项目为 Flask 应用，不再使用 Streamlit，故清除缓存为空操作；
若后续需要服务端缓存，可在此处接入内存/Redis 等实现。
"""

import hashlib
import functools
from typing import Optional, Callable


def make_cache_key(*args, **kwargs) -> str:
    """生成缓存键（供需要时使用）"""
    key_str = str(args) + str(sorted(kwargs.items()))
    return hashlib.md5(key_str.encode()).hexdigest()


def cached_query(ttl: int = 300):
    """缓存查询装饰器占位，直接执行原函数。"""
    def decorator(func: Callable) -> Callable:
        return func
    return decorator


def clear_cache(pattern: Optional[str] = None) -> None:
    """清除缓存。当前无 Streamlit/服务端缓存，为空操作。"""
    pass


def clear_related_cache(ledger_id: Optional[int] = None, account_id: Optional[int] = None) -> None:
    """
    清除与特定账本或账户相关的缓存。
    当前无 Streamlit/服务端缓存，为空操作；保留接口以兼容 database 等调用。
    """
    pass


def cached_dataframe(ttl: int = 300, show_spinner: bool = True):
    """DataFrame 缓存装饰器占位，直接返回原函数。"""
    def decorator(func: Callable) -> Callable:
        return func
    return decorator


def cached_dict(ttl: int = 300, show_spinner: bool = True):
    """字典缓存装饰器占位，直接返回原函数。"""
    def decorator(func: Callable) -> Callable:
        return func
    return decorator
