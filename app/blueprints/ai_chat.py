"""
AI 聊天蓝图 - 支持 OpenAI 通用格式，支持思维链显示
"""

import json
import logging

import requests
from flask import Blueprint, request, current_app, Response
from flask import session

from app.utils import api_success, api_error

ai_bp = Blueprint("ai_chat", __name__)

_DEFAULT_AI = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o-mini",
    "show_thinking": True,
    "context_messages": 20,
}


def _get_ai_config():
    """从 config.yaml 读取 AI 配置"""
    try:
        from utils.auth_config import load_config
        cfg = load_config(current_app.config.get("CONFIG_PATH"))
        ai = (cfg or {}).get("ai") or {}
        out = _DEFAULT_AI.copy()
        for k, v in ai.items():
            if v is not None:
                out[k] = v
        return out
    except Exception:
        return _DEFAULT_AI


def _save_ai_config(cfg: dict) -> bool:
    """保存 AI 配置到 config.yaml"""
    try:
        from utils.auth_config import load_config, save_config
        full = load_config(current_app.config.get("CONFIG_PATH")) or {}
        full["ai"] = cfg
        return save_config(current_app.config.get("CONFIG_PATH"), full)
    except Exception:
        return False


def _check_admin():
    """检查当前用户是否为管理员"""
    from utils.auth_config import load_config, is_admin, get_user
    if not session.get("username"):
        return False, "未登录"
    cfg = load_config(current_app.config.get("CONFIG_PATH"))
    user = get_user(cfg or {}, session["username"])
    if not is_admin(user.get("roles")):
        return False, "仅管理员可操作"
    return True, None


@ai_bp.route("/api/ai/config", methods=["GET"])
def get_ai_config():
    """获取 AI 配置（仅管理员，API Key 掩码）"""
    ok, err = _check_admin()
    if not ok:
        return api_error(err, 401 if "未登录" in err else 403)
    cfg = _get_ai_config()
    out = {
        "base_url": cfg.get("base_url", _DEFAULT_AI["base_url"]),
        "api_key": "***" if cfg.get("api_key") else "",
        "model": cfg.get("model", _DEFAULT_AI["model"]),
        "show_thinking": cfg.get("show_thinking", True),
        "context_messages": int(cfg.get("context_messages", _DEFAULT_AI["context_messages"])),
    }
    return api_success(data=out)


@ai_bp.route("/api/ai/config", methods=["PUT"])
def save_ai_config():
    """保存 AI 配置（仅管理员）"""
    ok, err = _check_admin()
    if not ok:
        return api_error(err, 401 if "未登录" in err else 403)
    body = request.get_json() or {}
    cfg = _get_ai_config()
    if "base_url" in body and body["base_url"]:
        cfg["base_url"] = body["base_url"].rstrip("/")
    if "api_key" in body:
        val = body["api_key"]
        if val and val != "***":
            cfg["api_key"] = val
    if "model" in body and body["model"]:
        cfg["model"] = body["model"]
    if "show_thinking" in body:
        cfg["show_thinking"] = bool(body["show_thinking"])
    if "context_messages" in body:
        val = body["context_messages"]
        try:
            n = int(val)
            cfg["context_messages"] = max(1, min(100, n))
        except (ValueError, TypeError):
            pass
    if not _save_ai_config(cfg):
        return api_error("保存配置失败", 500)
    return api_success(message="AI 配置已保存")


@ai_bp.route("/api/ai/chat", methods=["POST"])
def chat():
    """
    聊天接口 - 支持 OpenAI 通用格式
    支持 streaming，支持思维链（reasoning_content）
    """
    body = request.get_json() or {}
    messages = body.get("messages", [])
    stream = body.get("stream", True)

    if not messages:
        return api_error("messages 不能为空", 400)

    cfg = _get_ai_config()
    base_url = cfg.get("base_url", _DEFAULT_AI["base_url"]).rstrip("/")
    api_key = cfg.get("api_key", "")
    model = cfg.get("model", _DEFAULT_AI["model"])
    context_messages = int(cfg.get("context_messages", _DEFAULT_AI["context_messages"]))

    if not api_key:
        return api_error("请先在设置中配置 AI API Key", 400)

    # 对话记忆：保留 system + 最近 context_messages 条消息
    system_msg = [messages[0]] if messages and messages[0].get("role") == "system" else []
    rest = messages[1:] if system_msg else messages
    messages = system_msg + rest[-context_messages:] if context_messages > 0 else system_msg + rest

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }

    try:
        if stream:
            return _stream_response(url, headers, payload)
        return _non_stream_response(url, headers, payload)
    except requests.exceptions.RequestException as e:
        logging.exception("AI chat request failed")
        return api_error(str(e) or "请求失败", 500)


def _stream_response(url, headers, payload):
    """流式响应 - 支持 OpenAI 格式，解析 reasoning_content 作为思维链"""
    resp = requests.post(url, headers=headers, json=payload, stream=True, timeout=120)
    resp.raise_for_status()

    def generate():
        for line in resp.iter_lines():
            if not line or line == b"data: [DONE]":
                continue
            if line.startswith(b"data: "):
                data = line[6:]
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                # 思维链：reasoning_content（o1/o3 等推理模型）
                if "reasoning_content" in delta and delta["reasoning_content"]:
                    yield f"data: {json.dumps({'type': 'thinking', 'content': delta['reasoning_content']})}\n\n"
                # 正文内容
                if "content" in delta and delta["content"]:
                    yield f"data: {json.dumps({'type': 'content', 'content': delta['content']})}\n\n"
                # 兼容 content 为数组（部分模型）
                content_parts = delta.get("content")
                if isinstance(content_parts, list):
                    for part in content_parts:
                        if isinstance(part, dict):
                            if part.get("type") == "input_text":
                                t = part.get("text", "")
                                if t:
                                    yield f"data: {json.dumps({'type': 'thinking', 'content': t})}\n\n"
                            elif part.get("type") == "text" or "text" in part:
                                t = part.get("text", "")
                                if t:
                                    yield f"data: {json.dumps({'type': 'content', 'content': t})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _non_stream_response(url, headers, payload):
    """非流式响应"""
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        return api_error("模型返回空响应", 500)

    msg = choices[0].get("message", {})
    content_parts = msg.get("content", "")
    content = ""
    thinking = ""

    # 解析 content 数组（支持思维链）
    if isinstance(content_parts, list):
        texts = []
        thoughts = []
        for part in content_parts:
            if isinstance(part, dict):
                if part.get("type") == "input_text":
                    thoughts.append(part.get("text", ""))
                elif part.get("type") == "text":
                    texts.append(part.get("text", ""))
                elif "text" in part:
                    texts.append(part["text"])
        content = "".join(texts)
        thinking = "".join(thoughts)
    else:
        content = content_parts if isinstance(content_parts, str) else ""

    return api_success(data={"content": content, "thinking": thinking})
