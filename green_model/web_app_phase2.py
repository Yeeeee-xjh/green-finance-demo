"""数绿融通 phase2 工作台公网部署主入口。

本地运行默认 127.0.0.1:8530，云端自动读取 PORT 环境变量并监听 0.0.0.0。
支持密码管理员登录，普通访客默认只读，管理员登录后可执行写操作。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import logging
import os
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote
from wsgiref.simple_server import WSGIRequestHandler, make_server

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from green_model.phase2_ui.app import Phase2Application  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("green_phase2")

# 公网默认只读，可通过环境变量关闭
PUBLIC_READONLY = os.getenv("PUBLIC_READONLY", "1") != "0"
# 管理员密码：本地开发默认admin123，公网必须通过环境变量覆盖
DEFAULT_LOCAL_PASSWORD = "admin123"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", DEFAULT_LOCAL_PASSWORD if not os.getenv("PORT") else "")
# Cookie签名密钥，基于管理员密码自动生成，无需额外配置
COOKIE_SECRET = hashlib.sha256((ADMIN_PASSWORD + "green_finance_cookie_salt").encode()).digest()
SESSION_COOKIE_NAME = "green_admin_session"
SESSION_VALID_SECONDS = 7 * 24 * 3600  # 登录有效期7天

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    ),
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


def parse_cookies(environ: dict) -> dict[str, str]:
    """解析请求Cookie。"""
    raw_cookie = environ.get("HTTP_COOKIE", "")
    cookies = {}
    for part in raw_cookie.split(";"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            cookies[key.strip()] = unquote(value.strip())
    return cookies


def sign_session(payload: str) -> str:
    """对会话内容做HMAC签名，返回安全Cookie值。"""
    signature = hmac.new(COOKIE_SECRET, payload.encode(), hashlib.sha256).digest()
    return quote(base64.b64encode(payload.encode() + b"." + signature).decode())


def verify_session(cookie_value: str) -> bool:
    """验证管理员会话Cookie是否合法有效。"""
    try:
        raw = base64.b64decode(unquote(cookie_value))
        payload_bytes, signature = raw.rsplit(b".", 1)
        payload = payload_bytes.decode()
        expected_sig = hmac.new(COOKIE_SECRET, payload.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected_sig):
            return False
        # 校验过期时间
        issued_at = int(payload.split("|")[1])
        return time.time() - issued_at < SESSION_VALID_SECONDS
    except Exception:
        return False


def is_admin(environ: dict) -> bool:
    """判断当前请求是否为已登录管理员。"""
    cookies = parse_cookies(environ)
    session = cookies.get(SESSION_COOKIE_NAME)
    return bool(session and verify_session(session))


def render_login_page(error: str = "") -> str:
    """渲染管理员登录页，保持现有深绿商务风格。"""
    error_html = f'<div style="color:#c0392b;margin-bottom:16px;font-size:14px">{error}</div>' if error else ""
    return f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>管理员登录 - 数绿融通</title>
        <style>
            * {{ box-sizing: border-box; margin:0; padding:0; }}
            body {{ font-family: system-ui, -apple-system, sans-serif; background:#f5f8f7; min-height:100vh; display:flex; align-items:center; justify-content:center; padding:20px; }}
            .login-card {{ background:#fff; border-radius:12px; box-shadow:0 4px 20px rgba(15,93,79,0.08); padding:40px; width:100%; max-width:400px; }}
            .title {{ color:#0F5D4F; font-size:22px; font-weight:600; margin-bottom:8px; }}
            .subtitle {{ color:#666; font-size:14px; margin-bottom:28px; }}
            label {{ display:block; font-size:14px; color:#333; margin-bottom:8px; font-weight:500; }}
            input {{ width:100%; padding:12px 14px; border:1px solid #d0d7d5; border-radius:8px; font-size:14px; margin-bottom:20px; outline:none; }}
            input:focus {{ border-color:#0F5D4F; box-shadow:0 0 0 3px rgba(15,93,79,0.1); }}
            button {{ width:100%; background:#0F5D4F; color:#fff; border:none; border-radius:8px; padding:13px; font-size:15px; font-weight:500; cursor:pointer; }}
            button:hover {{ background:#0c4a3f; }}
            .back-link {{ display:block; text-align:center; margin-top:18px; color:#0F5D4F; font-size:13px; text-decoration:none; }}
        </style>
    </head>
    <body>
        <div class="login-card">
            <div class="title">管理员登录</div>
            <div class="subtitle">登录后可执行上传、修改、新建案件等操作</div>
            {error_html}
            <form method="POST" action="/admin/login">
                <label for="password">管理员密码</label>
                <input type="password" id="password" name="password" required autofocus placeholder="请输入管理员密码">
                <button type="submit">登录</button>
            </form>
            <a href="/dashboard" class="back-link">返回只读工作台</a>
        </div>
    </body>
    </html>
    """


class SilentHandler(WSGIRequestHandler):
    """隐藏服务器版本，简化日志，不记录敏感信息。"""

    server_version = "GreenFinanceDemo/1.0"
    sys_version = ""

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        logger.info("%s - %s", self.address_string(), format % args)


def build_wsgi_app() -> callable:
    """构建WSGI应用，单例初始化业务应用。"""
    app = Phase2Application()

    def wsgi(environ: dict, start_response) -> list[bytes]:
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")
        admin = is_admin(environ)

        # 健康检查接口，不依赖业务逻辑
        if path == "/health":
            body = b'{"status":"ok","service":"green-finance-demo","readonly":' + (
                b"false" if admin else b"true"
            ) + b',"admin":' + (b"true" if admin else b"false") + b"}"
            headers = [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ]
            for k, v in SECURITY_HEADERS.items():
                headers.append((k, v))
            start_response("200 OK", headers)
            return [body]

        # 管理员退出登录
        if path == "/admin/logout":
            headers = [
                ("Location", "/dashboard"),
                ("Set-Cookie", f"{SESSION_COOKIE_NAME}=; HttpOnly; SameSite=Strict; Max-Age=0; Path=/"),
            ]
            start_response("303 See Other", headers)
            logger.info("管理员退出登录")
            return [b""]

        # 管理员登录页面与提交
        if path == "/admin/login":
            if not ADMIN_PASSWORD:
                body = render_login_page("公网环境未配置管理员密码，登录入口已禁用。").encode("utf-8")
                headers = [
                    ("Content-Type", "text/html; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                ]
                start_response("403 Forbidden", headers)
                return [body]

            if method == "GET":
                body = render_login_page().encode("utf-8")
                headers = [
                    ("Content-Type", "text/html; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                ]
                for k, v in SECURITY_HEADERS.items():
                    headers.append((k, v))
                start_response("200 OK", headers)
                return [body]

            # POST登录验证
            content_length = int(environ.get("CONTENT_LENGTH") or 0)
            post_body = environ["wsgi.input"].read(content_length).decode()
            form = parse_qs(post_body)
            input_password = (form.get("password") or [""])[0]

            if not hmac.compare_digest(input_password, ADMIN_PASSWORD):
                body = render_login_page("密码错误，请重试。").encode("utf-8")
                headers = [
                    ("Content-Type", "text/html; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                ]
                start_response("401 Unauthorized", headers)
                logger.info("管理员登录密码错误")
                return [body]

            # 登录成功，生成签名会话
            session_payload = f"admin|{int(time.time())}"
            cookie_value = sign_session(session_payload)
            is_https = bool(environ.get("HTTPS") or environ.get("HTTP_X_FORWARDED_PROTO") == "https")
            cookie_attrs = f"{SESSION_COOKIE_NAME}={cookie_value}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_VALID_SECONDS}"
            if is_https:
                cookie_attrs += "; Secure"
            headers = [
                ("Location", "/dashboard"),
                ("Set-Cookie", cookie_attrs),
            ]
            start_response("303 See Other", headers)
            logger.info("管理员登录成功")
            return [b""]

        # 只读模式拦截非管理员的所有POST写操作
        if method == "POST" and PUBLIC_READONLY and not admin:
            body = (
                '{"error":"公网演示为只读模式，写入、上传、修改功能已关闭，请管理员登录后操作。","login_url":"/admin/login"}'
            ).encode("utf-8")
            headers = [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Allow", "GET"),
            ]
            for k, v in SECURITY_HEADERS.items():
                headers.append((k, v))
            start_response("405 Method Not Allowed", headers)
            logger.info("只读模式拦截匿名POST请求: %s", path)
            return [body]

        query = parse_qs(environ.get("QUERY_STRING", ""))
        try:
            if method == "GET":
                response = app.handle_get(path, query)
            elif method == "POST":
                content_length = int(environ.get("CONTENT_LENGTH") or 0)
                body = environ["wsgi.input"].read(content_length) if content_length else b""
                content_type = environ.get("CONTENT_TYPE", "application/x-www-form-urlencoded")
                response = app.handle_post(path, body, content_type)
            else:
                response = app.handle_get(path, query)
                response.status = 405
        except Exception as exc:  # noqa: BLE001
            # 公网不暴露错误堆栈和本地路径
            logger.error("请求处理异常 path=%s: %s", path, type(exc).__name__)
            error_body = (
                '{"error":"服务暂时不可用，请稍后重试。公网演示环境不包含敏感数据。"}'
            ).encode("utf-8")
            headers = [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(error_body))),
            ]
            for k, v in SECURITY_HEADERS.items():
                headers.append((k, v))
            start_response("500 Internal Server Error", headers)
            return [error_body]

        headers = []
        for k, v in response.headers.items():
            headers.append((k, v))
        for k, v in SECURITY_HEADERS.items():
            # 不覆盖业务自定义头
            if k not in response.headers:
                headers.append((k, v))

        status_text = {
            200: "200 OK",
            302: "302 Found",
            303: "303 See Other",
            400: "400 Bad Request",
            401: "401 Unauthorized",
            403: "403 Forbidden",
            404: "404 Not Found",
            405: "405 Method Not Allowed",
            409: "409 Conflict",
            413: "413 Payload Too Large",
            415: "415 Unsupported Media Type",
        }.get(response.status, f"{response.status} Unknown")
        start_response(status_text, headers)
        return [response.body]

    return wsgi


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="数绿融通 phase2 工作台")
    # 云端默认0.0.0.0，本地默认127.0.0.1
    default_host = "0.0.0.0" if os.getenv("PORT") else "127.0.0.1"
    default_port = int(os.getenv("PORT", "8530"))
    parser.add_argument("--host", default=default_host, help="监听地址")
    parser.add_argument("--port", type=int, default=default_port, help="监听端口")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    wsgi_app = build_wsgi_app()
    httpd = make_server(args.host, args.port, wsgi_app, handler_class=SilentHandler)
    logger.info(
        "数绿融通工作台启动，监听 %s:%s，公网只读模式=%s，管理员入口=%s",
        args.host,
        args.port,
        PUBLIC_READONLY,
        bool(ADMIN_PASSWORD),
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("服务收到停止信号，正在关闭")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
