import http.server, socketserver, os
from urllib.parse import unquote

DIR = os.path.abspath(r"C:\Users\Honor\Desktop\aigenis-parser\.demo-dist")
PORT = 5176

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
