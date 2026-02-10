"""
Fino AI 智能助手插件

基于 OpenAI 兼容 API 的 AI 聊天，支持思维链显示。
"""

from app.plugins.interface import PluginInterface, PluginManifest
from app.blueprints.ai_chat import ai_bp


class Plugin(PluginInterface):
    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            id="fino-ai-chat",
            name="AI 智能助手",
            version="1.0.0",
            description="基于 OpenAI 兼容 API 的 AI 聊天助手，支持思维链显示、上下文记忆",
            author="Fino",
            homepage="",
            repository="",
            license="MIT",
            min_fino_version="1.0",
            dependencies=[],
            api_prefix="/api/ai",
            nav_item=None,
            settings_tab={"id": "ai-chat", "label": "AI 配置", "icon": "smart_toy"},
            floating_widget={"id": "ai-chat-button", "label": "AI 助手"},
        )

    def register(self, app) -> None:
        if ai_bp.name not in app.blueprints:
            app.register_blueprint(ai_bp)

    def unregister(self, app) -> None:
        # 不实际移除蓝图：Flask 无法安全移除 url_map 中的路由，且 check_plugin_enabled 会拦截请求返回 404
        pass
