from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime
from urllib.parse import urlparse, parse_qs


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        action = params.get("action", ["hello"])[0]

        if action == "hello":
            body = {
                "message": "Hello from the Python API! 🐍",
                "status": "ok",
            }
        elif action == "time":
            body = {
                "current_time": datetime.now().isoformat(),
                "timezone": "UTC (server)",
                "status": "ok",
            }
        elif action == "echo":
            text = params.get("text", ["nothing sent"])[0]
            body = {
                "echo": text,
                "length": len(text),
                "reversed": text[::-1],
                "status": "ok",
            }
        elif action == "math":
            try:
                a = float(params.get("a", [0])[0])
                b = float(params.get("b", [0])[0])
                body = {
                    "a": a,
                    "b": b,
                    "sum": a + b,
                    "difference": a - b,
                    "product": a * b,
                    "quotient": a / b if b != 0 else "cannot divide by zero",
                    "status": "ok",
                }
            except ValueError:
                body = {"error": "Invalid numbers provided", "status": "error"}
        else:
            body = {"error": f"Unknown action: {action}", "status": "error"}

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body, indent=2).encode())
