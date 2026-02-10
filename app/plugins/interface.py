"""
Fino 插件接口规范

任何人可按照此接口开发插件，实现 install()、uninstall()、register()、unregister() 方法。
插件通过 manifest 声明元数据，通过 register() 注册 Flask 蓝图、路由等。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PluginManifest:
    """插件清单 - 声明插件的元数据，用于插件中心展示与依赖检查"""

    id: str  # 唯一标识，如 fino-ai-chat
    name: str  # 显示名称
    version: str  # 语义化版本，如 1.0.0
    description: str  # 简短描述
    author: str  # 作者
    homepage: str = ""  # 项目主页
    repository: str = ""  # 代码仓库
    license: str = ""  # 许可证
    min_fino_version: str = ""  # 最低 Fino 版本要求
    dependencies: list[str] = field(default_factory=list)  # 依赖的其他插件 id
    # 插件路由前缀，用于禁用检查
    api_prefix: str = ""
    # 前端扩展
    nav_item: Optional[dict] = None  # 侧边栏入口，如 {"id": "cloud-storage", "label": "网盘", "icon": "cloud"}
    settings_tab: Optional[dict] = None  # 设置页 Tab，如 {"id": "cloudreve", "label": "网盘", "icon": "cloud"}
    floating_widget: Optional[dict] = None  # 悬浮组件，如 AI 聊天按钮
    # 配置 schema（可选，用于验证插件配置）
    config_schema: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "homepage": self.homepage,
            "repository": self.repository,
            "license": self.license,
            "min_fino_version": self.min_fino_version,
            "dependencies": self.dependencies,
            "api_prefix": self.api_prefix,
            "nav_item": self.nav_item,
            "settings_tab": self.settings_tab,
            "floating_widget": self.floating_widget,
            "config_schema": self.config_schema,
        }


class PluginInterface(ABC):
    """
    插件接口 - 所有 Fino 插件必须实现此接口

    开发步骤：
    1. 继承 PluginInterface
    2. 实现 get_manifest() 返回元数据
    3. 实现 register(app) 注册 Flask 蓝图等
    4. 实现 unregister(app) 清理资源
    5. 可选实现 install()、uninstall() 做数据库迁移等
    """

    @abstractmethod
    def get_manifest(self) -> PluginManifest:
        """返回插件清单"""
        pass

    @abstractmethod
    def register(self, app: Any) -> None:
        """
        注册插件到应用
        - 注册 Flask Blueprint
        - 注册路由
        - 注入扩展逻辑
        """
        pass

    @abstractmethod
    def unregister(self, app: Any) -> None:
        """
        从应用卸载插件
        - 移除 Blueprint
        - 清理资源
        """
        pass

    def install(self, app: Any) -> None:
        """
        安装时调用（可选）
        - 创建数据库表
        - 初始化配置
        """
        pass

    def uninstall(self, app: Any) -> None:
        """
        卸载时调用（可选）
        - 删除数据库表
        - 清理配置
        """
        pass

    def on_enable(self, app: Any) -> None:
        """启用时调用（可选）"""
        pass

    def on_disable(self, app: Any) -> None:
        """禁用时调用（可选）"""
        pass
