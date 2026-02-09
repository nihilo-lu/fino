"""
缓存工具模块
提供缓存装饰器和缓存管理功能，减少数据库查询和计算压力
"""

import streamlit as st
import hashlib
import functools
from typing import Optional, Any, Callable
import logging


def make_cache_key(*args, **kwargs) -> str:
    """生成缓存键
    
    Args:
        *args: 位置参数
        **kwargs: 关键字参数
        
    Returns:
        str: 缓存键
    """
    # 将参数转换为字符串并生成哈希
    key_str = str(args) + str(sorted(kwargs.items()))
    return hashlib.md5(key_str.encode()).hexdigest()


def cached_query(ttl: int = 300):
    """
    缓存数据库查询结果的装饰器
    
    Args:
        ttl: 缓存过期时间（秒），默认300秒（5分钟）
    
    使用示例:
        @cached_query(ttl=300)
        def get_data(db, ledger_id):
            return db.get_ledgers()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{func.__name__}_{make_cache_key(*args, **kwargs)}"
            
            # 尝试从缓存获取
            if cache_key in st.session_state.get('_query_cache', {}):
                cached_data, cached_time = st.session_state['_query_cache'][cache_key]
                import time
                if time.time() - cached_time < ttl:
                    logging.debug(f"缓存命中: {func.__name__}")
                    return cached_data
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            if '_query_cache' not in st.session_state:
                st.session_state['_query_cache'] = {}
            import time
            st.session_state['_query_cache'][cache_key] = (result, time.time())
            logging.debug(f"缓存更新: {func.__name__}")
            return result
        
        return wrapper
    return decorator


def clear_cache(pattern: Optional[str] = None):
    """
    清除缓存
    
    Args:
        pattern: 缓存键模式（可选），如果提供则只清除匹配的缓存，否则清除所有缓存
    """
    if '_query_cache' not in st.session_state:
        return
    
    if pattern:
        # 清除匹配模式的缓存
        keys_to_remove = [
            key for key in st.session_state['_query_cache'].keys()
            if pattern in key
        ]
        for key in keys_to_remove:
            del st.session_state['_query_cache'][key]
        logging.info(f"清除缓存: {len(keys_to_remove)} 个匹配 '{pattern}' 的缓存项")
    else:
        # 清除所有缓存
        count = len(st.session_state['_query_cache'])
        st.session_state['_query_cache'] = {}
        logging.info(f"清除所有缓存: {count} 个缓存项")


def clear_related_cache(ledger_id: Optional[int] = None, account_id: Optional[int] = None):
    """
    清除与特定账本或账户相关的缓存
    
    注意：Streamlit 的 @st.cache_data 缓存是基于函数签名和参数的哈希。
    当数据更新后，我们需要清除相关函数的缓存以确保数据一致性。
    为了简化实现，我们清除所有 Streamlit 缓存数据，虽然这可能会影响一些性能，
    但能确保数据一致性，且数据更新操作不频繁。
    
    Args:
        ledger_id: 账本ID（可选）
        account_id: 账户ID（可选）
    """
    try:
        # 清除自定义的查询缓存（如果有）
        if '_query_cache' in st.session_state:
            keys_to_remove = []
            for key in list(st.session_state['_query_cache'].keys()):
                should_remove = False
                
                # 如果指定了 ledger_id，检查缓存键是否包含该账本ID
                if ledger_id is not None and str(ledger_id) in key:
                    should_remove = True
                
                # 如果指定了 account_id，检查缓存键是否包含该账户ID
                if account_id is not None and str(account_id) in key:
                    should_remove = True
                
                # 清除通用的查询缓存
                if any(func_name in key for func_name in [
                    'get_ledgers', 'get_accounts', 'get_currencies', 
                    'get_categories', 'get_positions', 'get_portfolio_stats',
                    'get_transactions', 'get_fund_transactions'
                ]):
                    should_remove = True
                
                if should_remove:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del st.session_state['_query_cache'][key]
        
        # 清除所有 Streamlit 缓存数据
        # 这确保了数据更新后，所有相关缓存都会失效
        try:
            st.cache_data.clear()
            logging.info(f"已清除 Streamlit 缓存 (ledger_id={ledger_id}, account_id={account_id})")
        except AttributeError:
            # 某些 Streamlit 版本可能不支持 clear() 方法
            # 在这种情况下，缓存会在 TTL 过期后自动失效
            logging.warning("当前 Streamlit 版本不支持清除缓存，缓存将在 TTL 过期后自动失效")
        except Exception as e:
            logging.warning(f"清除 Streamlit 缓存时发生错误: {e}")
            
    except Exception as e:
        # 如果清除缓存时出错，记录日志但不影响主流程
        logging.warning(f"清除缓存时发生错误: {e}")


# 使用 Streamlit 的缓存装饰器包装函数
def cached_dataframe(ttl: int = 300, show_spinner: bool = True):
    """
    使用 Streamlit 的 @st.cache_data 装饰器缓存 DataFrame 结果
    
    Args:
        ttl: 缓存过期时间（秒），默认300秒（5分钟）
        show_spinner: 是否显示加载动画
    
    使用示例:
        @cached_dataframe(ttl=300)
        def get_data(db, ledger_id):
            return db.get_ledgers()
    """
    def decorator(func: Callable) -> Callable:
        @st.cache_data(ttl=ttl, show_spinner=show_spinner)
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


def cached_dict(ttl: int = 300, show_spinner: bool = True):
    """
    使用 Streamlit 的 @st.cache_data 装饰器缓存字典结果
    
    Args:
        ttl: 缓存过期时间（秒），默认300秒（5分钟）
        show_spinner: 是否显示加载动画
    
    使用示例:
        @cached_dict(ttl=300)
        def get_stats(db, ledger_id):
            return db.get_portfolio_stats(ledger_id)
    """
    def decorator(func: Callable) -> Callable:
        @st.cache_data(ttl=ttl, show_spinner=show_spinner)
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator
