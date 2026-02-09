"""
Fino 插件管理器

负责插件的加载、启用、禁用、安装、卸载。
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

from app.plugins.interface import PluginInterface, PluginManifest

logger = logging.getLogger(__name__)


class PluginManager:
    """插件管理器：发现、加载、注册插件"""

    def __init__(self, app: Any = None, plugins_dir: Optional[str] = None):
        self.app = app
        self._plugins_dir = plugins_dir
        self._loaded: dict[str, PluginInterface] = {}
        self._enabled: set[str] = set()
        self._base_dir: Optional[Path] = None
        if app:
            self.init_app(app)

    def init_app(self, app: Any) -> None:
        """初始化并绑定到 Flask 应用"""
        self.app = app
        # 项目根目录（static_folder 的父目录）
        base_dir = Path(app.static_folder or ".").parent
        self._base_dir = base_dir
        self._plugins_dir = self._plugins_dir or str(base_dir / "plugins")
        if not os.path.exists(self._plugins_dir):
            os.makedirs(self._plugins_dir, exist_ok=True)
        # 确保 plugins 目录在 Python 路径中
        if self._plugins_dir not in sys.path:
            sys.path.insert(0, self._plugins_dir)

    def _get_enabled_list_path(self) -> Path:
        """已启用插件列表的存储路径（config 同目录）"""
        if self._base_dir:
            return self._base_dir / "conf" / "enabled_plugins.json"
        return Path("conf") / "enabled_plugins.json"

    def _load_enabled_list(self) -> set[str]:
        """加载已启用插件列表。若文件不存在，默认启用内置插件以保持向后兼容"""
        path = self._get_enabled_list_path()
        if not path.exists():
            #  backward compat: 默认启用 AI 和网盘
            default_enabled = {"fino-ai-chat", "fino-cloudreve"}
            self._save_enabled_list(default_enabled)
            return default_enabled
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get("enabled", []))
        except Exception as e:
            logger.warning("加载 enabled_plugins.json 失败: %s", e)
            return set()

    def _save_enabled_list(self, enabled: set[str]) -> bool:
        """保存已启用插件列表"""
        path = self._get_enabled_list_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"enabled": list(enabled)}, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error("保存 enabled_plugins.json 失败: %s", e)
            return False

    def discover_installed(self) -> list[dict]:
        """
        发现已安装的插件（plugins 目录下的子目录，含 plugin.py 或 __init__.py 导出 Plugin）
        返回 [{"id": "xxx", "path": "...", "manifest": {...}}, ...]
        """
        result = []
        if not os.path.isdir(self._plugins_dir):
            return result
        for name in os.listdir(self._plugins_dir):
            plugin_path = os.path.join(self._plugins_dir, name)
            if not os.path.isdir(plugin_path):
                continue
            # 查找 plugin.py 或 __init__.py
            for entry in ("plugin.py", "__init__.py"):
                fp = os.path.join(plugin_path, entry)
                if os.path.isfile(fp):
                    manifest = self._load_manifest_from_file(fp, name)
                    if manifest:
                        result.append({
                            "id": manifest.get("id", name),
                            "path": plugin_path,
                            "name": name,
                            "manifest": manifest,
                        })
                    break
        return result

    def _load_manifest_from_file(self, filepath: str, default_id: str) -> Optional[dict]:
        """从插件文件加载 manifest（通过导入模块并调用 get_manifest）"""
        try:
            spec = importlib.util.spec_from_file_location("plugin_temp", filepath)
            if not spec or not spec.loader:
                return None
            mod = importlib.util.module_from_spec(spec)
            sys.modules["plugin_temp"] = mod
            spec.loader.exec_module(mod)
            # 获取 Plugin 类实例
            plugin = getattr(mod, "Plugin", None) or getattr(mod, "plugin", None)
            if plugin and callable(plugin):
                inst = plugin() if not isinstance(plugin, type) else plugin()
                if hasattr(inst, "get_manifest"):
                    m = inst.get_manifest()
                    return m.to_dict() if hasattr(m, "to_dict") else m
            return None
        except Exception as e:
            logger.debug("加载插件 manifest 失败 %s: %s", filepath, e)
            return None

    def load_plugin(self, plugin_id: str) -> Optional[PluginInterface]:
        """加载单个插件实例"""
        installed = self.discover_installed()
        for item in installed:
            if item["id"] == plugin_id:
                return self._load_plugin_from_path(item["path"], item.get("name", plugin_id))
        return None

    def _load_plugin_from_path(self, plugin_path: str, module_name: str) -> Optional[PluginInterface]:
        """从路径加载插件"""
        for entry in ("plugin", "__init__"):
            fp = os.path.join(plugin_path, f"{entry}.py")
            if not os.path.isfile(fp):
                continue
            try:
                rel_name = os.path.basename(plugin_path).replace("-", "_").replace(" ", "_")
                full_name = f"fino_plugin_{rel_name}_{entry}"
                spec = importlib.util.spec_from_file_location(full_name, fp, submodule_search_locations=[plugin_path])
                if not spec or not spec.loader:
                    continue
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                plugin = getattr(mod, "Plugin", None) or getattr(mod, "plugin", None)
                if plugin:
                    inst = plugin() if not isinstance(plugin, type) else plugin()
                    if isinstance(inst, PluginInterface):
                        return inst
            except Exception as e:
                logger.exception("加载插件失败 %s: %s", plugin_path, e)
        return None

    def get_enabled(self) -> set[str]:
        """获取当前已启用的插件 ID 集合"""
        return self._load_enabled_list()

    def enable_plugin(self, plugin_id: str) -> bool:
        """启用插件"""
        plugin = self.load_plugin(plugin_id)
        if not plugin:
            return False
        enabled = self._load_enabled_list()
        enabled.add(plugin_id)
        if not self._save_enabled_list(enabled):
            return False
        self._enabled.add(plugin_id)
        if self.app and plugin_id not in self._loaded:
            self._loaded[plugin_id] = plugin
            plugin.register(self.app)
            if hasattr(plugin, "on_enable"):
                plugin.on_enable(self.app)
        return True

    def disable_plugin(self, plugin_id: str) -> bool:
        """禁用插件"""
        enabled = self._load_enabled_list()
        enabled.discard(plugin_id)
        if not self._save_enabled_list(enabled):
            return False
        self._enabled.discard(plugin_id)
        if plugin_id in self._loaded:
            plugin = self._loaded[plugin_id]
            if hasattr(plugin, "on_disable"):
                plugin.on_disable(self.app)
            plugin.unregister(self.app)
            del self._loaded[plugin_id]
        return True

    def uninstall_plugin(self, plugin_id: str) -> bool:
        """卸载插件：从 plugins 目录移除插件文件夹"""
        if plugin_id not in {p["id"] for p in self.discover_installed()}:
            return False
        if plugin_id in self._enabled:
            self.disable_plugin(plugin_id)
        for item in self.discover_installed():
            if item["id"] == plugin_id:
                import shutil
                path = item.get("path")
                if path and os.path.isdir(path):
                    try:
                        shutil.rmtree(path)
                        return True
                    except OSError as e:
                        logger.error("卸载插件失败 %s: %s", plugin_id, e)
                        return False
        return False

    def install_builtin(self, plugin_id: str) -> bool:
        """安装内置插件：从 app.plugins.builtin 复制到 plugins 目录"""
        import shutil
        builtin_ids = {"fino-ai-chat", "fino-cloudreve"}
        if plugin_id not in builtin_ids:
            return False
        target = os.path.join(self._plugins_dir, plugin_id)
        if os.path.isdir(target):
            return True  # 已安装
        app_plugins = Path(__file__).parent
        source = app_plugins / "builtin" / plugin_id
        if not source.is_dir():
            return False
        try:
            shutil.copytree(str(source), target)
            return True
        except OSError as e:
            logger.error("安装插件失败 %s: %s", plugin_id, e)
            return False

    def load_and_register_all(self) -> None:
        """加载并注册所有已启用的插件"""
        enabled = self._load_enabled_list()
        self._enabled = enabled
        for plugin_id in enabled:
            plugin = self.load_plugin(plugin_id)
            if plugin:
                self._loaded[plugin_id] = plugin
                plugin.register(self.app)
                logger.info("已加载插件: %s", plugin_id)
            else:
                logger.warning("插件 %s 加载失败，已跳过", plugin_id)

    def get_registered_manifests(self) -> list[dict]:
        """获取当前已注册插件的 manifest 列表"""
        result = []
        for plugin_id, plugin in self._loaded.items():
            m = plugin.get_manifest()
            d = m.to_dict() if hasattr(m, "to_dict") else m
            d["enabled"] = True
            result.append(d)
        return result

    def get_plugin_state(self) -> dict:
        """获取插件状态概要（供 API 使用）"""
        installed = self.discover_installed()
        enabled = self._load_enabled_list()
        return {
            "installed": [
                {
                    "id": item["id"],
                    "name": item["manifest"].get("name", item["id"]),
                    "version": item["manifest"].get("version", ""),
                    "enabled": item["id"] in enabled,
                    "manifest": item["manifest"],
                }
                for item in installed
            ],
            "enabled": list(enabled),
        }
