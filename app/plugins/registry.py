"""
Fino 插件中心 - 插件注册表

提供可安装插件的发现与元数据。可扩展为从远程 URL 拉取注册表。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 内置插件中心数据（可替换为远程 JSON URL）
DEFAULT_REGISTRY = [
    {
        "id": "fino-ai-chat",
        "name": "AI 智能助手",
        "version": "1.0.0",
        "description": "基于 OpenAI 兼容 API 的 AI 聊天助手，支持思维链显示、上下文记忆",
        "author": "Fino",
        "homepage": "",
        "repository": "",
        "license": "MIT",
        "min_fino_version": "1.0",
        "dependencies": [],
        "nav_item": None,
        "settings_tab": {"id": "ai-chat", "label": "AI 配置", "icon": "smart_toy"},
        "floating_widget": {"id": "ai-chat-button", "label": "AI 助手"},
        "download_url": "",  # 空表示内置，由本地 plugins 目录提供
        "install_type": "builtin",  # builtin | git | url
    },
    {
        "id": "fino-cloudreve",
        "name": "Cloudreve 网盘",
        "version": "1.0.0",
        "description": "绑定 Cloudreve 网盘，在 Fino 中管理、上传、下载文件",
        "author": "Fino",
        "homepage": "https://cloudrevev4.apifox.cn/",
        "repository": "",
        "license": "MIT",
        "min_fino_version": "1.0",
        "dependencies": [],
        "nav_item": {"id": "cloud-storage", "label": "网盘", "icon": "cloud"},
        "settings_tab": {"id": "cloudreve", "label": "网盘", "icon": "cloud"},
        "floating_widget": None,
        "download_url": "",
        "install_type": "builtin",
    },
]


class PluginRegistry:
    """插件中心 - 管理可安装插件的注册表"""

    def __init__(self, registry_url: Optional[str] = None):
        self.registry_url = registry_url
        self._cache: Optional[list[dict]] = None

    def get_registry_path(self) -> Optional[Path]:
        """获取本地注册表文件路径（conf/plugin_registry.json）"""
        # 尝试从项目根推断
        for base in [Path.cwd(), Path(__file__).parent.parent.parent]:
            conf = base / "conf" / "plugin_registry.json"
            if conf.exists():
                return conf
        return Path("conf") / "plugin_registry.json"

    def _load_local_registry(self) -> list[dict]:
        """加载本地自定义注册表"""
        path = self.get_registry_path()
        if path and path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("plugins", [])
            except Exception as e:
                logger.warning("加载 plugin_registry.json 失败: %s", e)
        return []

    def fetch_registry(self) -> list[dict]:
        """
        获取插件中心完整列表
        合并：内置 + 本地 conf/plugin_registry.json + 远程（若配置）
        """
        if self._cache is not None:
            return self._cache
        registry = list(DEFAULT_REGISTRY)
        local = self._load_local_registry()
        for p in local:
            if not any(r.get("id") == p.get("id") for r in registry):
                registry.append(p)
        self._cache = registry
        return registry

    def get_plugin_info(self, plugin_id: str) -> Optional[dict]:
        """根据 id 获取插件信息"""
        for p in self.fetch_registry():
            if p.get("id") == plugin_id:
                return p
        return None

    def invalidate_cache(self) -> None:
        """清除缓存"""
        self._cache = None
