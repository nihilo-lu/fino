"""
数据库抽象基类 - 多数据库支持
定义统一的数据库管理器接口，支持 SQLite、PostgreSQL 等
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Protocol


class DBManagerBase(Protocol):
    """数据库管理器基类协议 - 所有数据库实现需遵循此接口"""

    def get_connection(self) -> Any:
        """获取数据库连接，返回的连接需支持 cursor()、commit()、rollback()、close()"""
        ...

    def close(self) -> None:
        """关闭数据库连接"""
        ...


def get_db_manager(
    db_type: str = "sqlite",
    db_path: str = "investment.db",
    pg_host: str = "localhost",
    pg_port: int = 5432,
    pg_database: str = "investment",
    pg_user: str = "postgres",
    pg_password: str = "",
    pg_sslmode: str = "prefer",
) -> DBManagerBase:
    """
    根据配置创建对应的数据库管理器

    Args:
        db_type: 数据库类型，'sqlite' 或 'postgresql'
        db_path: SQLite 数据库文件路径（仅 sqlite 时使用）
        pg_host, pg_port, pg_database, pg_user, pg_password, pg_sslmode: PostgreSQL 连接参数

    Returns:
        DBManagerBase 实例
    """
    if db_type == "postgresql":
        from utils.db_postgres_manager import PostgreSQLManager
        return PostgreSQLManager(
            host=pg_host,
            port=pg_port,
            database=pg_database,
            user=pg_user,
            password=pg_password,
            sslmode=pg_sslmode,
        )
    else:
        from utils.db_sqlite_manager import SQLiteManager
        return SQLiteManager(db_path)
