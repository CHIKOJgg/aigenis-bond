import http.server
import os
import socketserver
from urllib.parse import unquote

# Папка со сборкой демо-SPA. По умолчанию — каталог .demo-dist в корне
# репозитория; можно переопределить переменной окружения DEMO_DIST_DIR.
DIR = os.environ.get(
    "DEMO_DIST_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".demo-dist")),
)
PORT = int(os.environ.get("DEMO_PORT", "5176"))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=DIR, **k)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        fpath = os.path.normpath(os.path.join(DIR, unquote(path).lstrip("/")))
        if os.path.isfile(fpath):
            self.path = path
        else:
            self.path = "/index.html"  # SPA fallback
        return super().do_GET()

    def do_HEAD(self):
        return self.do_GET()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    print(f"Serving demo SPA at http://localhost:{PORT} (from {DIR})")
    with Server(("127.0.0.1", PORT), Handler) as httpd:
        httpd.serve_forever()
