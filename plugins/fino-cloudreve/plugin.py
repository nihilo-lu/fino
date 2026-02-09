"""
Fino Cloudreve 网盘插件

绑定 Cloudreve 网盘，支持文件管理、上传、下载。
"""

from app.plugins.interface import PluginInterface, PluginManifest
from app.blueprints.cloudreve import cloudreve_bp


class Plugin(PluginInterface):
    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            id="fino-cloudreve",
            name="Cloudreve 网盘",
            version="1.0.0",
            description="绑定 Cloudreve 网盘，在 Fino 中管理、上传、下载文件",
            author="Fino",
            homepage="https://cloudrevev4.apifox.cn/",
            repository="",
            license="MIT",
            min_fino_version="1.0",
            dependencies=[],
            nav_item={"id": "cloud-storage", "label": "网盘", "icon": "cloud"},
            settings_tab={"id": "cloudreve", "label": "网盘", "icon": "cloud"},
            floating_widget=None,
        )

    def register(self, app) -> None:
        if cloudreve_bp.name not in app.blueprints:
            app.register_blueprint(cloudreve_bp)

    def unregister(self, app) -> None:
        # 不实际移除蓝图：Flask 无法安全移除 url_map 中的路由，且 check_plugin_enabled 会拦截请求返回 404
        pass
