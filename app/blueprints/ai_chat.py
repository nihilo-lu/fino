"""
AI 聊天蓝图 - 支持 OpenAI 通用格式，支持思维链显示
"""

import json
import logging

import requests
from flask import Blueprint, request, current_app, Response
from flask import session

from app.utils import api_success, api_error
from app.auth_middleware import get_token_from_request, verify_token

ai_bp = Blueprint("ai_chat", __name__)

_DEFAULT_SYSTEM_PROMPT = """你是一个投资理财助手，帮助用户分析投资组合、理解收益数据、给出合理建议。回答要简洁专业，适当使用数据支撑。
当用户询问账本、账户、交易、持仓、收益等数据且已开启「调用数据」时，你可使用 execute_python 工具在沙箱中执行 Python 调用本应用 API。代码中可用 requests、json、API_BASE、CURRENT_USERNAME（当前登录用户名，调用需 username 的接口时必传，如 /api/ledgers?username= 等）。请将需要返回的结果赋给变量 result。"""

_DEFAULT_AI = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o-mini",
    "show_thinking": True,
    "context_messages": 20,
    "avatar_url": "",
    "system_prompt": _DEFAULT_SYSTEM_PROMPT,
}


def _get_ai_config():
    """从 config.yaml 读取 AI 配置（支持 lab.ai 与旧版 ai）"""
    try:
        from utils.auth_config import load_config
        cfg = load_config(current_app.config.get("CONFIG_PATH"))
        ai = (cfg or {}).get("lab", {}).get("ai") or (cfg or {}).get("ai") or {}
        out = _DEFAULT_AI.copy()
        for k, v in ai.items():
            if v is not None:
                out[k] = v
        return out
    except Exception:
        return _DEFAULT_AI


def _save_ai_config(cfg: dict) -> bool:
    """保存 AI 配置到 config.yaml（lab.ai）"""
    try:
        from utils.auth_config import load_config, save_config
        full = load_config(current_app.config.get("CONFIG_PATH")) or {}
        if "lab" not in full:
            full["lab"] = {}
        full["lab"]["ai"] = cfg
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


def _get_current_username():
    """当前用户名：优先 Bearer Token，否则 Session"""
    token = get_token_from_request()
    if token:
        payload = verify_token(token)
        if payload:
            return payload.get("username")
    return session.get("username")


def _get_current_user_api_token():
    """获取当前用户的 API Token（用于沙箱内请求本应用 API）"""
    username = _get_current_username()
    if not username:
        return None, "未登录"
    try:
        from utils.auth_config import load_config
        cfg = load_config(current_app.config.get("CONFIG_PATH")) or {}
        user = (cfg.get("credentials") or {}).get("usernames") or {}
        user = user.get(username) or {}
        token = user.get("api_token")
        return token, None
    except Exception as e:
        logging.exception("Get api_token error")
        return None, str(e)


def _is_admin():
    ok, _ = _check_admin()
    return ok


@ai_bp.route("/api/ai/config", methods=["GET"])
def get_ai_config():
    """获取 AI 配置：未登录 403；管理员返回完整配置（API Key 掩码）；非管理员仅返回聊天用公开项（含 system_prompt）"""
    if not _get_current_username():
        return api_error("未登录", 401)
    cfg = _get_ai_config()
    if _is_admin():
        out = {
            "base_url": cfg.get("base_url", _DEFAULT_AI["base_url"]),
            "api_key": "***" if cfg.get("api_key") else "",
            "model": cfg.get("model", _DEFAULT_AI["model"]),
            "show_thinking": cfg.get("show_thinking", True),
            "context_messages": int(cfg.get("context_messages", _DEFAULT_AI["context_messages"])),
            "avatar_url": cfg.get("avatar_url", "") or "",
            "system_prompt": cfg.get("system_prompt") or _DEFAULT_SYSTEM_PROMPT,
        }
    else:
        out = {
            "model": cfg.get("model", _DEFAULT_AI["model"]),
            "show_thinking": cfg.get("show_thinking", True),
            "context_messages": int(cfg.get("context_messages", _DEFAULT_AI["context_messages"])),
            "avatar_url": cfg.get("avatar_url", "") or "",
            "system_prompt": cfg.get("system_prompt") or _DEFAULT_SYSTEM_PROMPT,
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
    if "avatar_url" in body:
        cfg["avatar_url"] = (body["avatar_url"] or "").strip()
    if "system_prompt" in body:
        cfg["system_prompt"] = (body["system_prompt"] or "").strip() or _DEFAULT_SYSTEM_PROMPT
    if not _save_ai_config(cfg):
        return api_error("保存配置失败", 500)
    return api_success(message="AI 配置已保存")


@ai_bp.route("/api/ai/execute", methods=["POST"])
def execute_sandbox():
    """
    沙箱执行 Python 代码。需登录；使用当前用户的 API Token 请求本应用 API。
    请求体: { "code": "..." }
    代码中可使用: requests (仅限请求本应用)、json、API_BASE，并将最终结果赋给 result。
    """
    api_token, err = _get_current_user_api_token()
    if err:
        return api_error(err, 401 if "未登录" in err else 500)
    body = request.get_json() or {}
    code = body.get("code") or ""
    if not code.strip():
        return api_error("code 不能为空", 400)
    api_base = request.url_root.rstrip("/")
    username = _get_current_username() or ""
    from app.sandbox import run_python_sandbox
    out = run_python_sandbox(code=code, api_base=api_base, api_token=api_token or "", username=username)
    if out.get("error") and not out.get("ok"):
        return api_success(data=out, message=out["error"])  # 仍返回 200，便于前端展示 stdout/error
    return api_success(data=out)


# 沙箱工具定义（OpenAI tools 格式）
EXECUTE_PYTHON_TOOL = {
    "type": "function",
    "function": {
        "name": "execute_python",
        "description": "在沙箱中执行 Python 代码，用于调用本应用 API 获取账本、账户、交易、组合、收益等数据。可用变量：requests、json、API_BASE、CURRENT_USERNAME（当前登录用户名，调用需 username 的接口时必须使用，例如 requests.get(f\"/api/ledgers?username={CURRENT_USERNAME}\")）。请将需要返回的结果赋给变量 result。",
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "要执行的 Python 代码"}},
            "required": ["code"],
        },
    },
}


@ai_bp.route("/api/ai/chat", methods=["POST"])
def chat():
    """
    聊天接口 - 支持 OpenAI 通用格式
    支持 streaming，支持思维链（reasoning_content）
    """
    body = request.get_json() or {}
    messages = body.get("messages", [])
    stream = body.get("stream", True)
    use_tools = body.get("use_tools", False)

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

    # 本轮的附件（图片等）注入到最后一条 user 消息
    attachments = body.get("attachments") or []
    if attachments and messages:
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                text = messages[i].get("content") or ""
                if isinstance(text, list):
                    text = "".join(
                        p.get("text", "") for p in text if isinstance(p, dict) and p.get("type") == "text"
                    )
                parts = [{"type": "text", "text": text or " "}]
                for att in attachments:
                    if att.get("type") == "image" and att.get("data"):
                        mime = att.get("mime") or "image/png"
                        url = f"data:{mime};base64,{att['data']}"
                        parts.append({"type": "image_url", "image_url": {"url": url}})
                messages[i] = {**messages[i], "content": parts}
                break

    if use_tools:
        try:
            content, thinking, executions = _chat_with_tools(base_url, api_key, model, messages)
            return api_success(data={
                "content": content,
                "thinking": thinking or "",
                "executions": executions or [],
            })
        except requests.exceptions.RequestException as e:
            logging.exception("AI chat with tools failed")
            return api_error(str(e) or "请求失败", 500)

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


def _chat_with_tools(base_url: str, api_key: str, model: str, messages: list, max_rounds: int = 5):
    """带 execute_python 工具的对话：非流式，遇到 tool_calls 则执行沙箱并继续请求。返回 (content, thinking, executions)。"""
    from app.sandbox import run_python_sandbox
    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    api_token, err = _get_current_user_api_token()
    if err or not api_token:
        raise RuntimeError(err or "未登录或未生成 API Token，无法使用沙箱")
    api_base = request.url_root.rstrip("/")
    username = _get_current_username() or ""
    current = list(messages)
    last_thinking = ""
    executions = []
    for _ in range(max_rounds):
        payload = {"model": model, "messages": current, "stream": False, "tools": [EXECUTE_PYTHON_TOOL]}
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return "模型返回空响应", last_thinking, executions
        msg = choices[0].get("message", {})
        content = msg.get("content") or ""
        last_thinking = msg.get("reasoning_content") or ""
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return content, last_thinking, executions
        current.append(msg)
        for tc in tool_calls:
            tid = tc.get("id") or ""
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            args_str = fn.get("arguments") or "{}"
            if name != "execute_python":
                current.append({"role": "tool", "tool_call_id": tid, "content": "未实现的工具"})
                continue
            try:
                args = json.loads(args_str)
                code = (args.get("code") or "").strip()
            except (json.JSONDecodeError, TypeError):
                current.append({"role": "tool", "tool_call_id": tid, "content": json.dumps({"ok": False, "error": "参数无效"})})
                executions.append({"code": "", "ok": False, "stdout": "", "error": "参数无效", "result": None})
                continue
            out = run_python_sandbox(code=code, api_base=api_base, api_token=api_token, username=username, timeout=25)
            current.append({"role": "tool", "tool_call_id": tid, "content": json.dumps(out)})
            executions.append({
                "code": code,
                "ok": out.get("ok", False),
                "stdout": out.get("stdout") or "",
                "error": out.get("error"),
                "result": out.get("result"),
            })
    return "达到最大工具调用轮数", last_thinking, executions


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
