from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class SpaRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:
        requested = self.translate_path(self.path)
        path = Path(requested)
        if self.path.startswith("/api/") or self.path.startswith("/@vite"):
            self.send_error(404, "Not found")
            return

        if path.exists():
            return super().do_GET()

        self.path = "/index.html"
        return super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve frontend/dist with SPA fallback.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent / "dist"))
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Frontend root not found: {root}")

    def factory(*f_args, **f_kwargs):
        return SpaRequestHandler(*f_args, directory=str(root), **f_kwargs)

    server = ThreadingHTTPServer((args.host, args.port), factory)
    print(f"Serving Stacky frontend on http://{args.host}:{args.port} from {root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
