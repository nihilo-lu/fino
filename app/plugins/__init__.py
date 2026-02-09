"""
Fino 插件系统 - 开放式扩展架构

支持插件式扩展，任何人可按照接口规范开发插件并上架至插件中心。
"""

from app.plugins.interface import PluginInterface, PluginManifest
from app.plugins.manager import PluginManager

__all__ = ["PluginInterface", "PluginManifest", "PluginManager"]
