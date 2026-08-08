#!/usr/bin/env python3
"""Local read/write server for the memory overview.

    python3 scripts/serve.py [--port 8000] [--no-browser]

Serves the same site `build_site.py` publishes, plus a small JSON API under
`/api/` that writes back into `memory/`. The generated pages detect that API
and unlock in-page editing; on GitHub Pages the identical files stay read-only
because nothing answers `/api/`.

Why a local server rather than a browser CMS: every Git-backed CMS (Decap,
Sveltia, TinaCMS) needs an external OAuth broker to commit from a static page,
and this knowledge base is deliberately infrastructure-free. Editing locally
against the working tree keeps git as the only write path, and every mutation
goes through the same `kb.py` helpers the CLI uses, so both agree.

No third-party dependencies — stdlib only, same as the rest of the KB tooling.
"""
import argparse
import http.server
import json
import pathlib
import shutil
import sys
import tempfile
import threading
import webbrowser
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_site  # noqa: E402
from kb import (  # noqa: E402
    CONFIDENCE_LEVELS,
    ROOT,
    TYPES,
    _append_log,
    resolve,
    triage_report,
    verify_detail,
    write_body,
    write_frontmatter,
)

# Serialized so two concurrent requests cannot interleave a rebuild with a write.
LOCK = threading.Lock()


class ApiError(Exception):
    """A request that failed for a reason worth showing the user verbatim."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _entry(name):
    hit = resolve(name)
    if hit is None:
        raise ApiError(f"no entry named '{name}'", status=404)
    return hit


def _known_names():
    return {fm.get("name", path.stem) for _, path, fm, _ in _all()}


def _all():
    from kb import iter_entries, parse_frontmatter

    out = []
    for t, path in iter_entries():
        try:
            fm, body = parse_frontmatter(path)
        except OSError:
            continue
        out.append((t, path, fm, body))
    return out


def api_capabilities(_payload, _name):
    """Told the page what it may offer; its absence is what keeps Pages read-only."""
    return {
        "editable": True,
        "root": str(ROOT),
        "confidence": CONFIDENCE_LEVELS,
        "types": TYPES,
    }


def api_update(payload, name):
    entry_type, path, fm, _ = _entry(name)
    changes = {}

    if "description" in payload:
        desc = str(payload["description"]).strip()
        if not desc:
            raise ApiError("description cannot be empty")
        changes["description"] = desc

    if "confidence" in payload:
        conf = str(payload["confidence"]).strip()
        if conf not in CONFIDENCE_LEVELS:
            raise ApiError(f"confidence must be one of {', '.join(CONFIDENCE_LEVELS)}")
        changes["confidence"] = conf

    if "links" in payload:
        links = payload["links"]
        if not isinstance(links, list):
            raise ApiError("links must be a list")
        links = [str(x).strip() for x in links if str(x).strip()]
        known = _known_names()
        for target in links:
            if target == name:
                raise ApiError("an entry cannot link to itself")
            if target not in known:
                raise ApiError(f"no entry named '{target}' — refusing to create a dangling link")
        changes["links"] = links

    if changes:
        write_frontmatter(path, changes)
    if "body" in payload:
        write_body(path, str(payload["body"]))

    if changes or "body" in payload:
        fields = ", ".join(sorted(set(changes) | ({"body"} if "body" in payload else set())))
        _append_log(entry_type, path.stem, date.today().isoformat(), "updated", fields)
    return {"ok": True, "name": name, "changed": sorted(changes)}


def api_verify(payload, name):
    entry_type, path, _, _ = _entry(name)
    today = date.today().isoformat()
    changes = {"last_verified": today}
    conf = payload.get("confidence")
    if conf:
        if conf not in CONFIDENCE_LEVELS:
            raise ApiError(f"confidence must be one of {', '.join(CONFIDENCE_LEVELS)}")
        changes["confidence"] = conf
    write_frontmatter(path, changes)
    # Same formatter as the CLI and the MCP server, so one review trail reads
    # the same however the verification was made. `note` is optional here and
    # the built page does not send one yet — a browser verify is a person at a
    # keyboard, who can say what they checked in the field if the UI grows one.
    _append_log(entry_type, path.stem, today, "verified",
                verify_detail(conf or "?", payload.get("note")))
    return {"ok": True, "name": name, "last_verified": today}


def api_delete(payload, name):
    entry_type, path, _, _ = _entry(name)
    referrers = [
        (p, fm) for _, p, fm, _ in _all()
        if name in (fm.get("links") or []) and fm.get("name") != name
    ]
    if referrers and not payload.get("force"):
        names = ", ".join(fm.get("name", p.stem) for p, fm in referrers)
        raise ApiError(f"still linked from: {names} — resend with force to strip those links")
    for p, fm in referrers:
        write_frontmatter(p, {"links": [ln for ln in fm["links"] if ln != name]})
    path.unlink()
    _append_log(entry_type, path.stem, date.today().isoformat(), "deleted")
    return {"ok": True, "name": name, "unlinked_from": [p.stem for p, _ in referrers]}


def api_triage(_payload, _name):
    return {"ok": True, "triage": triage_report()}


# path prefix -> (handler, takes a trailing entry name)
ROUTES = {
    "capabilities": (api_capabilities, False),
    "triage": (api_triage, False),
    "entry": (api_update, True),
    "verify": (api_verify, True),
    "delete": (api_delete, True),
}


def make_handler(site_dir: pathlib.Path, rebuild):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(site_dir), **kw)

        def log_message(self, fmt, *args):  # quieter than the stdlib default
            if not self.path.startswith("/api/"):
                return
            sys.stderr.write(f"{self.command} {self.path} — {fmt % args}\n")

        def _json(self, status, payload):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _dispatch(self, payload):
            parts = self.path.lstrip("/").split("/")[1:]  # drop "api"
            if not parts or not parts[0]:
                raise ApiError("unknown endpoint", status=404)
            route = ROUTES.get(parts[0])
            if route is None:
                raise ApiError(f"unknown endpoint '{parts[0]}'", status=404)
            handler, needs_name = route
            name = "/".join(parts[1:]) or None
            if needs_name and not name:
                raise ApiError(f"endpoint '{parts[0]}' needs an entry name", status=404)
            from urllib.parse import unquote

            return handler(payload, unquote(name) if name else None)

        def do_GET(self):
            if self.path.startswith("/api/"):
                try:
                    with LOCK:
                        self._json(200, self._dispatch({}))
                except ApiError as e:
                    self._json(e.status, {"error": str(e)})
                return
            super().do_GET()

        def do_POST(self):
            if not self.path.startswith("/api/"):
                self._json(404, {"error": "not found"})
                return
            length = int(self.headers.get("content-length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
                if not isinstance(payload, dict):
                    raise ApiError("body must be a JSON object")
                with LOCK:
                    result = self._dispatch(payload)
                    rebuild()  # the page reloads straight after a write
                self._json(200, result)
            except ApiError as e:
                self._json(e.status, {"error": str(e)})
            except json.JSONDecodeError:
                self._json(400, {"error": "body is not valid JSON"})
            except Exception as e:  # surface the reason instead of a blank 500
                self._json(500, {"error": f"{type(e).__name__}: {e}"})

    return Handler


def serve(port=8000, open_browser=True, site_dir=None):
    tmp = None
    if site_dir is None:
        tmp = tempfile.mkdtemp(prefix="kb-site-")
        site_dir = pathlib.Path(tmp)
    site_dir = pathlib.Path(site_dir)
    slug = build_site.repo_slug()

    def rebuild():
        build_site.build(site_dir, slug)

    rebuild()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(site_dir, rebuild))
    url = f"http://127.0.0.1:{server.server_port}/"
    # flushed so a supervising process can read the port off stdout immediately
    print(f"serving {ROOT} at {url} — editing enabled, writes go straight to memory/", flush=True)
    print("stop with ctrl-c", flush=True)
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Serve the memory overview with editing enabled.")
    ap.add_argument("--port", type=int, default=8000, help="port to listen on (default: 8000)")
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser")
    ap.add_argument("--out", help="directory to build into (default: a temporary one)")
    args = ap.parse_args(argv)
    return serve(port=args.port, open_browser=not args.no_browser, site_dir=args.out)


if __name__ == "__main__":
    sys.exit(main())
