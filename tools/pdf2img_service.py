#!/usr/bin/env python3
"""
PDF -> JPEG conversion service for the Order-to-Invoice workflow.

The n8n container runs a Docker Hardened Image, which ships without a package
manager, so poppler/ImageMagick cannot be installed inside it. Instead n8n calls
this service on the host - the same way it already calls Ollama on
host.docker.internal.

Conversion uses macOS `sips`, which renders page 1 of a PDF. No dependencies.

    python3 pdf2img_service.py            # listens on 0.0.0.0:8099

Endpoints
    GET  /health   -> {"ok": true, "converter": "sips"}
    POST /convert  -> {"pdf_base64": "...", "max_px": 1600}
                   <- {"jpeg_base64": "...", "jpeg_bytes": 143712}

From inside the n8n container the URL is:
    http://host.docker.internal:8099/convert

NOTE: binds 0.0.0.0 so Docker can reach it, which also exposes it to your local
network. It only converts PDFs and stores nothing, but don't run it on untrusted
networks. Ctrl+C to stop.
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.environ.get("PDF2IMG_HOST", "0.0.0.0")
PORT = int(os.environ.get("PDF2IMG_PORT", "8099"))
MAX_UPLOAD = 25 * 1024 * 1024  # 25 MB


def pdf_to_jpeg(pdf_bytes: bytes, max_px: int = 1600) -> bytes:
    """Render page 1 of a PDF to JPEG using macOS sips."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.pdf")
        dst = os.path.join(tmp, "out.jpg")
        with open(src, "wb") as fh:
            fh.write(pdf_bytes)

        result = subprocess.run(
            ["sips", "-s", "format", "jpeg", "-Z", str(max_px), src, "--out", dst],
            capture_output=True,
        )
        if result.returncode != 0 or not os.path.exists(dst):
            raise RuntimeError(
                f"sips failed (exit {result.returncode}): "
                f"{result.stderr.decode('utf-8', 'replace')[:400]}"
            )
        with open(dst, "rb") as fh:
            return fh.read()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "converter": "sips"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/convert":
            return self._send(404, {"error": "not found"})

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return self._send(400, {"error": "empty body"})
        if length > MAX_UPLOAD:
            return self._send(413, {"error": f"body over {MAX_UPLOAD} bytes"})

        raw = self.rfile.read(length)
        content_type = (self.headers.get("Content-Type") or "").lower()
        max_px = 1600

        if "json" in content_type:
            # {"pdf_base64": "...", "max_px": 1600}
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                return self._send(400, {"error": f"invalid JSON: {exc}"})

            b64 = payload.get("pdf_base64")
            if not b64:
                return self._send(400, {"error": "missing pdf_base64"})
            try:
                pdf = base64.b64decode(b64)
            except Exception as exc:
                return self._send(400, {"error": f"pdf_base64 not decodable: {exc}"})
            max_px = int(payload.get("max_px", 1600))
        else:
            # Raw PDF bytes - what n8n's HTTP Request node sends with
            # Body Content Type "n8n Binary File". No base64 anywhere.
            pdf = raw

        if not pdf.startswith(b"%PDF"):
            return self._send(400, {
                "error": "body is not a PDF (no %PDF header). "
                         f"Got {len(pdf)} bytes starting with {pdf[:16]!r}"
            })

        try:
            jpeg = pdf_to_jpeg(pdf, max_px)
        except Exception as exc:
            return self._send(500, {"error": str(exc)})

        self._send(200, {
            "jpeg_base64": base64.b64encode(jpeg).decode(),
            "jpeg_bytes": len(jpeg),
        })

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s - %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    if sys.platform != "darwin":
        sys.exit("This service uses macOS `sips`; run it on the Mac host.")
    print(f"PDF->JPEG service on http://{HOST}:{PORT}")
    print(f"  from the n8n container: http://host.docker.internal:{PORT}/convert")
    print("  Ctrl+C to stop\n")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
