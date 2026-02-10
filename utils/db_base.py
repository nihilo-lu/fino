"""
数据库抽象基类 - 多数据库支持
定义统一的数据库管理器接口，支持 SQLite、PostgreSQL、Cloudflare D1
"""

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
    config_path: Optional[str] = None,
    pg_host: str = "localhost",
    pg_port: int = 5432,
    pg_database: str = "investment",
    pg_user: str = "postgres",
    pg_password: str = "",
    pg_sslmode: str = "prefer",
    d1_account_id: str = "",
    d1_database_id: str = "",
    d1_api_token: str = "",
) -> DBManagerBase:
    """
    根据配置创建对应的数据库管理器

    Args:
        db_type: 数据库类型，'sqlite' | 'postgresql' | 'd1'
        db_path: SQLite 数据库文件路径（仅 sqlite 时使用）
        pg_*: PostgreSQL 连接参数
        d1_account_id, d1_database_id, d1_api_token: Cloudflare D1 连接参数

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
            config_path=config_path,
        )
    elif db_type == "d1":
        from utils.db_d1_manager import D1Manager
        return D1Manager(
            account_id=d1_account_id,
            database_id=d1_database_id,
            api_token=d1_api_token,
            config_path=config_path,
        )
    else:
        from utils.db_sqlite_manager import SQLiteManager
        return SQLiteManager(db_path=db_path, config_path=config_path)
