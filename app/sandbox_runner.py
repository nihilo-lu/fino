"""
沙箱内执行的引导脚本：从 stdin 读取用户代码，在受限环境中执行。
仅允许请求 API_BASE（环境变量），并使用 API_TOKEN 鉴权。
由 app.sandbox 通过 subprocess 调用，不可直接作为主模块对外暴露。
"""
import os
import sys
import json
import io

# 从环境变量读取，由父进程注入
API_BASE = (os.environ.get("SANDBOX_API_BASE") or "").rstrip("/")
API_TOKEN = os.environ.get("SANDBOX_API_TOKEN") or ""
CURRENT_USERNAME = os.environ.get("SANDBOX_USERNAME") or ""


def _allowed_request(method, url, **kwargs):
    """只允许请求 SANDBOX_API_BASE 下的 URL，并自动加上 Authorization"""
    if not API_BASE or not url.startswith(API_BASE):
        raise ValueError("仅允许请求当前应用的 API 地址")
    headers = kwargs.get("headers") or {}
    headers = dict(headers)
    headers["Authorization"] = f"Bearer {API_TOKEN}"
    kwargs["headers"] = headers
    import requests as _requests
    return _requests.request(method, url, **kwargs)


class SafeRequests:
    """仅允许访问 API_BASE 的 requests 封装"""

    def get(self, path_or_url, **kwargs):
        url = path_or_url if path_or_url.startswith("http") else f"{API_BASE}{path_or_url}"
        return _allowed_request("GET", url, **kwargs)

    def post(self, path_or_url, **kwargs):
        url = path_or_url if path_or_url.startswith("http") else f"{API_BASE}{path_or_url}"
        return _allowed_request("POST", url, **kwargs)

    def put(self, path_or_url, **kwargs):
        url = path_or_url if path_or_url.startswith("http") else f"{API_BASE}{path_or_url}"
        return _allowed_request("PUT", url, **kwargs)

    def delete(self, path_or_url, **kwargs):
        url = path_or_url if path_or_url.startswith("http") else f"{API_BASE}{path_or_url}"
        return _allowed_request("DELETE", url, **kwargs)


def main():
    if not API_BASE:
        out = json.dumps({"error": "SANDBOX_API_BASE 未设置", "stdout": "", "result": None})
        print(out, flush=True)
        sys.exit(1)

    code = sys.stdin.read()
    # 模型返回的代码常为 JSON 转义：字面量 \\n、\\"、\\' 等，需还原为真实字符，否则 exec 报 line continuation 等错误
    code = (
        code.replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\r", "\r")
        .replace('\\"', '"')
        .replace("\\'", "'")
    )
    out_capture = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = out_capture

    # 受限 builtins：禁止 open/exec/eval 等；提供安全 __import__ 仅允许 requests 与 json
    _b = __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__
    _safe = {
        k: _b[k] for k in (
            "print", "len", "str", "int", "float", "list", "dict", "tuple", "set",
            "range", "enumerate", "zip", "map", "filter", "sorted", "reversed",
            "min", "max", "sum", "abs", "round", "isinstance", "bool", "type",
            "None", "True", "False", "Exception", "KeyError", "ValueError", "IndexError",
            "AssertionError", "AttributeError", "TypeError", "ZeroDivisionError",
            "getattr", "setattr", "hasattr", "callable", "iter", "next",
            "repr", "format", "ord", "chr", "divmod", "pow", "all", "any",
            "slice", "object", "list", "dict", "set", "frozenset", "bytes", "str", "int", "float",
        )
        if k in _b
    }

    safe_globals = {
        "json": json,
        "requests": SafeRequests(),
        "API_BASE": API_BASE,
        "API_TOKEN": "",  # 不暴露给用户代码
        "CURRENT_USERNAME": CURRENT_USERNAME,
        "result": None,
        "__builtins__": _safe,
    }

    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in ("requests", "json"):
            return safe_globals[name]
        raise ImportError(f"仅允许 import requests 与 json，不允许: {name}")
    _safe["__import__"] = _safe_import

    def _serializable(val):
        if val is None or isinstance(val, (bool, int, float, str)):
            return val
        if isinstance(val, (list, tuple)):
            return [_serializable(x) for x in val]
        if isinstance(val, dict):
            return {str(k): _serializable(v) for k, v in val.items()}
        return repr(val)

    try:
        exec(code, safe_globals)
        result = safe_globals.get("result")
        result = _serializable(result)
    except Exception as e:
        sys.stdout = old_stdout
        out = json.dumps({
            "error": str(e),
            "stdout": out_capture.getvalue(),
            "result": None,
        })
        print(out, flush=True)
        sys.exit(0)  # 不 exit(1)，以便父进程从 stdout 解析 JSON

    sys.stdout = old_stdout
    out = json.dumps({
        "error": None,
        "stdout": out_capture.getvalue(),
        "result": result,
    })
    print(out, flush=True)


if __name__ == "__main__":
    main()
