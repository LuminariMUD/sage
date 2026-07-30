#!/usr/bin/env python3
"""Local-only HTTP server for the chat UI."""

import argparse
import http.server
import os
import socketserver
import sys
from pathlib import Path


class SecureUIRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serve static assets with defensive browser headers."""

    def log_message(self, format, *args):
        """Avoid logging request targets, which can contain query credentials."""
        status = args[1] if len(args) > 1 else "unknown"
        print(f"[UI] request completed ({status})")

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src http://localhost:* http://127.0.0.1:* https:; "
            "img-src 'self' data:; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'none'",
        )
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", nargs="?", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    # Change to the directory containing this script
    script_dir = Path(__file__).parent
    os.chdir(script_dir)

    try:
        with socketserver.ThreadingTCPServer(
            (args.host, args.port), SecureUIRequestHandler
        ) as httpd:
            print(f"🌐 Serving chat UI at: http://{args.host}:{args.port}")
            print(f"📁 Serving from: {script_dir}")
            print("🔧 Press Ctrl+C to stop")
            print()
            print(f"📖 Open your browser to: http://{args.host}:{args.port}/chat-ui.html")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Server stopped")
    except OSError as e:
        if e.errno == 48:  # Address already in use
            print(
                f"❌ Port {args.port} is already in use. "
                "Try a different port or stop the other server."
            )
        else:
            print(f"❌ Server error type: {type(e).__name__}")
        sys.exit(1)


if __name__ == "__main__":
    main()
