"""
配置加载工具模块
统一从 conf/main_config.ini 读取配置信息
"""

import configparser
import os
from typing import List, Optional

class ConfigLoader:
    """配置加载器类"""
    
    def __init__(self, config_path: str = None):
        """
        初始化配置加载器
        
        Args:
            config_path: 配置文件路径，默认为 conf/main_config.ini
        """
        if config_path is None:
            # 获取项目根目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            config_path = os.path.join(project_root, 'conf', 'main_config.ini')
        
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self.config.read(config_path, encoding='utf-8')
    
    def get(self, section: str, key: str, fallback: Optional[str] = None) -> str:
        """
        获取配置值
        
        Args:
            section: 配置节名称
            key: 配置键名
            fallback: 默认值
            
        Returns:
            配置值字符串
        """
        return self.config.get(section, key, fallback=fallback)
    
    def getint(self, section: str, key: str, fallback: Optional[int] = None) -> int:
        """获取整数配置值"""
        return self.config.getint(section, key, fallback=fallback)
    
    def getfloat(self, section: str, key: str, fallback: Optional[float] = None) -> float:
        """获取浮点数配置值"""
        return self.config.getfloat(section, key, fallback=fallback)
    
    def getboolean(self, section: str, key: str, fallback: Optional[bool] = None) -> bool:
        """获取布尔值配置值"""
        return self.config.getboolean(section, key, fallback=fallback)
    
    def getlist(self, section: str, key: str, fallback: Optional[List[str]] = None) -> List[str]:
        """
        获取列表配置值（逗号分隔的字符串）
        
        Args:
            section: 配置节名称
            key: 配置键名
            fallback: 默认值列表
            
        Returns:
            配置值列表
        """
        value = self.get(section, key)
        if value:
            return [item.strip() for item in value.split(',') if item.strip()]
        return fallback if fallback is not None else []
    
    # Schema 配置
    @property
    def SCHEMA_NAME(self) -> str:
        """获取 Schema 名称"""
        return self.get('schema', 'schema_name')
    
    # 表名配置
    @property
    def TABLE_NAME(self) -> str:
        """交易明细表名"""
        return self.get('tables', 'table_name')
    
    @property
    def FUND_DETAIL_TABLE_NAME(self) -> str:
        """资金明细表名"""
        return self.get('tables', 'fund_detail_table_name')
    
    @property
    def SNAPSHOT_TABLE_NAME(self) -> str:
        """持仓快照表名"""
        return self.get('tables', 'snapshot_table_name')
    
    @property
    def PL_TABLE_NAME(self) -> str:
        """交易收益表名"""
        return self.get('tables', 'pl_table_name')
    
    @property
    def ACCOUNT_SNAPSHOT_TABLE_NAME(self) -> str:
        """账户快照表名"""
        return self.get('tables', 'account_snapshot_table_name')
    
    @property
    def PRICE_TABLE_NAME(self) -> str:
        """价格库表名"""
        return self.get('tables', 'price_table_name')
    
    @property
    def UNREALIZED_PL_TABLE_NAME(self) -> str:
        """浮动损益表名"""
        return self.get('tables', 'unrealized_pl_table_name')
    
    @property
    def EXCHANGE_PL_TABLE_NAME(self) -> str:
        """汇兑损益表名"""
        return self.get('tables', 'exchange_pl_table_name')
    
    @property
    def RETURN_RATE_TABLE_NAME(self) -> str:
        """收益率表名"""
        return self.get('tables', 'return_rate_table_name')
    
    @property
    def ROUNDING_DIFF_TABLE_NAME(self) -> str:
        """尾差损益表名"""
        return self.get('tables', 'rounding_diff_table_name')
    
    @property
    def ACCOUNT_INFO_TABLE_NAME(self) -> str:
        """账户信息表名"""
        return self.get('tables', 'account_info_table_name')
    
    @property
    def BOOK_INFO_TABLE_NAME(self) -> str:
        """账本信息表名"""
        return self.get('tables', 'book_info_table_name')
    
    # 字段名配置
    @property
    def DATE_FIELD_NAME(self) -> str:
        """日期字段名"""
        return self.get('fields', 'date_field_name')
    
    @property
    def FIELDS_TO_FETCH(self) -> List[str]:
        """需要获取的字段列表"""
        return self.getlist('fields', 'fields_to_fetch', ['Id', '日期', 'CreatedAt', 'UpdatedAt'])
    
    # 缓存配置
    @property
    def CACHE_DIR(self) -> str:
        """缓存文件夹路径"""
        return self.get('cache', 'cache_dir', 'cache')
    
    def get_cache_file_path(self, filename_key: str) -> str:
        """
        获取缓存文件的完整路径
        
        Args:
            filename_key: 配置文件中缓存文件名的键（如 'snapshot_file'）
            
        Returns:
            缓存文件的完整路径
        """
        cache_dir = self.CACHE_DIR
        filename = self.get('cache', filename_key)
        return os.path.join(cache_dir, filename)
    
    @property
    def SNAPSHOT_FILE(self) -> str:
        """持仓快照缓存文件路径"""
        return self.get_cache_file_path('snapshot_file')
    
    @property
    def PL_FILE(self) -> str:
        """交易收益缓存文件路径"""
        return self.get_cache_file_path('pl_file')
    
    @property
    def ACCOUNT_SNAPSHOT_FILE(self) -> str:
        """账户快照缓存文件路径"""
        return self.get_cache_file_path('account_snapshot_file')
    
    @property
    def CACHE_FILE(self) -> str:
        """交易明细缓存文件路径"""
        return self.get_cache_file_path('inventory_cache_file')
    
    @property
    def FUND_DETAIL_CACHE_FILE(self) -> str:
        """资金明细缓存文件路径"""
        return self.get_cache_file_path('fund_detail_cache_file')
    
    @property
    def UNREALIZED_PL_FILE(self) -> str:
        """浮动损益缓存文件路径"""
        return self.get_cache_file_path('unrealized_pl_file')
    
    @property
    def RETURN_RATE_FILE(self) -> str:
        """收益率缓存文件路径"""
        return self.get_cache_file_path('return_rate_file')
    
    @property
    def ROUNDING_DIFF_FILE(self) -> str:
        """尾差损益缓存文件路径"""
        return self.get_cache_file_path('rounding_diff_file')
    
    # 性能配置
    @property
    def BATCH_SIZE(self) -> int:
        """批量写入大小"""
        return self.getint('performance', 'batch_size', 500)
    
    @property
    def REFRESH_DAYS(self) -> int:
        """价格刷新期（天数）"""
        return self.getint('performance', 'refresh_days', 20)

    @property
    def LIMIT(self) -> int:
        """分页查询每页记录数"""
        return self.getint('performance', 'limit', 1000)
    
    # 精度配置
    @property
    def SHARE_DECIMAL_PLACES(self) -> int:
        """份额保留小数位数"""
        return self.getint('precision', 'share_decimal_places', 4)
    
    @property
    def NAV_DECIMAL_PLACES(self) -> int:
        """净值保留小数位数"""
        return self.getint('precision', 'nav_decimal_places', 6)
    
    @property
    def RATE_DECIMAL_PLACES(self) -> int:
        """收益率保留小数位数"""
        return self.getint('precision', 'rate_decimal_places', 6)
    
    # 业务配置
    @property
    def REPORT_CURRENCY(self) -> str:
        """报表币种（用于净资产计算）"""
        return self.get('business', 'report_currency', 'CNY')


# 全局配置实例（单例模式）
_config_instance: Optional[ConfigLoader] = None

def get_config(config_path: str = None) -> ConfigLoader:
    """
    获取全局配置实例（单例模式）
    
    Args:
        config_path: 配置文件路径，仅在首次调用时有效
        
    Returns:
        ConfigLoader 实例
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigLoader(config_path)
    return _config_instance

