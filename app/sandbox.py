"""
沙箱执行：在子进程中运行用户提供的 Python 代码，仅允许请求本应用 API。
"""

import os
import sys
import json
import logging
import subprocess

logger = logging.getLogger(__name__)

# 默认超时（秒）
DEFAULT_TIMEOUT = 25
# 代码最大长度（字符）
MAX_CODE_LENGTH = 16 * 1024


def run_python_sandbox(
    code: str,
    api_base: str,
    api_token: str,
    username: str = "",
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """
    在沙箱中执行 Python 代码。

    - code: 用户代码，可访问 requests、json、API_BASE、CURRENT_USERNAME，并将最终结果赋给 result
    - api_base: 本应用 API 基地址
    - api_token: 当前用户的 API Token
    - username: 当前登录用户名，注入为沙箱内 CURRENT_USERNAME（供 /api/ledgers 等接口使用）
    - timeout: 子进程超时秒数

    返回: {"ok": bool, "stdout": str, "result": any, "error": str|None}
    """
    if not (api_base or "").strip():
        return {"ok": False, "stdout": "", "result": None, "error": "API 基地址未配置"}
    if not (api_token or "").strip():
        return {"ok": False, "stdout": "", "result": None, "error": "请先生成 API Token（设置 -> API Token）以便助手调用数据接口"}

    code = (code or "").strip()
    if len(code) > MAX_CODE_LENGTH:
        return {"ok": False, "stdout": "", "result": None, "error": f"代码长度不能超过 {MAX_CODE_LENGTH} 字符"}

    api_base = api_base.rstrip("/")
    runner_dir = os.path.dirname(os.path.abspath(__file__))
    runner_script = os.path.join(runner_dir, "sandbox_runner.py")
    if not os.path.isfile(runner_script):
        return {"ok": False, "stdout": "", "result": None, "error": "沙箱运行器未找到"}

    env = os.environ.copy()
    env["SANDBOX_API_BASE"] = api_base
    env["SANDBOX_API_TOKEN"] = api_token
    env["SANDBOX_USERNAME"] = username or ""

    try:
        proc = subprocess.run(
            [sys.executable, "-u", runner_script],
            input=code.encode("utf-8"),
            env=env,
            capture_output=True,
            timeout=timeout,
            cwd=runner_dir,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "result": None, "error": f"执行超时（{timeout} 秒）"}
    except Exception as e:
        logger.exception("Sandbox subprocess error")
        return {"ok": False, "stdout": "", "result": None, "error": str(e)}

    stderr_text = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
    stdout_raw = (proc.stdout or b"").decode("utf-8", errors="replace")

    # 最后一行应为 JSON
    lines = stdout_raw.strip().split("\n")
    last = lines[-1] if lines else ""
    try:
        data = json.loads(last)
        err = data.get("error")
        out = data.get("stdout", "")
        result = data.get("result")
        if err:
            return {"ok": False, "stdout": out, "result": result, "error": err}
        if stderr_text:
            out = (out + "\n" + stderr_text).strip()
        return {"ok": True, "stdout": out, "result": result, "error": None}
    except json.JSONDecodeError:
        return {
            "ok": False,
            "stdout": stdout_raw,
            "result": None,
            "error": stderr_text or "沙箱输出格式异常",
        }
