"""仅用于工作流测试的固定数据服务；无数据库、无第三方请求。"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        if url.path == "/order":
            order_id = query.get("order_id", [""])[0]
            orders = {
                "TEST-1001": {"status": "delivered", "days_since_delivery": 3, "amount": 129.9},
                "TEST-1002": {"status": "delivered", "days_since_delivery": 15, "amount": 59.0},
                "TEST-1003": {"status": "shipped", "days_since_delivery": 0, "amount": 89.0},
            }
            if order_id not in orders:
                self.reply(404, {"ok": False, "error": "order_not_found", "order_id": order_id[:40]})
            else:
                self.reply(200, {"ok": True, "order_id": order_id, **orders[order_id]})
        elif url.path == "/policy":
            category = query.get("category", [""])[0]
            if category != "standard":
                self.reply(404, {"ok": False, "error": "policy_not_found"})
            else:
                self.reply(200, {"ok": True, "category": "standard", "return_window_days": 7,
                                 "rule": "已签收且签收不超过7天，可申请退货；未签收或超期转人工。"})
        elif url.path == "/health":
            self.reply(200, {"ok": True, "fixture": "after-sales-v1"})
        else:
            self.reply(404, {"ok": False, "error": "not_found"})

    def reply(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"工作流测试服务：http://127.0.0.1:{server.server_port}（Ctrl+C 停止）", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
