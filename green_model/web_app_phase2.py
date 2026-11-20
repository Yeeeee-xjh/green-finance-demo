"""数绿融通 phase2 工作台公网部署主入口。

本地运行默认 127.0.0.1:8530，云端自动读取 PORT 环境变量并监听 0.0.0.0。
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs
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

        # 健康检查接口，不依赖业务逻辑
        if path == "/health":
            body = b'{"status":"ok","service":"green-finance-demo","readonly":' + (
                b"true" if PUBLIC_READONLY else b"false"
            ) + b"}"
            headers = [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ]
            for k, v in SECURITY_HEADERS.items():
                headers.append((k, v))
            start_response("200 OK", headers)
            return [body]

        # 公网只读模式拦截所有POST写操作
        if method == "POST" and PUBLIC_READONLY:
            body = (
                '{"error":"公网演示为只读模式，写入、上传、修改功能已关闭。"}'
            ).encode("utf-8")
            headers = [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Allow", "GET"),
            ]
            for k, v in SECURITY_HEADERS.items():
                headers.append((k, v))
            start_response("405 Method Not Allowed", headers)
            logger.info("只读模式拦截POST请求: %s", path)
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
        "数绿融通工作台启动，监听 %s:%s，公网只读模式=%s",
        args.host,
        args.port,
        PUBLIC_READONLY,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("服务收到停止信号，正在关闭")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
