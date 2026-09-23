"""EWVE, Ephraim's Web Video Editor. Usage: .venv/bin/python server.py "<project folder>" [port]"""
import json, os, sys, threading, subprocess, hashlib, urllib.parse, mimetypes, traceback
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import export

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.abspath(sys.argv[1]); PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 5177
MEDIA = os.path.join(PROJ, "Media"); PJSON = os.path.join(PROJ, "project.json")
THUMBS = os.path.join(PROJ, ".work", "thumbs"); os.makedirs(THUMBS, exist_ok=True)
lock = threading.Lock()
CHUNK = 2 * 1024 * 1024
job = {"state": "idle", "step": "", "k": 0, "n": 0, "out": "", "error": ""}
levels = {}  # "src|in|out" -> auto gain dB


def load(): return json.load(open(PJSON))


def probe_duration(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except ValueError: return 0.0


_sources = None
def sources():
    global _sources
    if _sources is None:
        _sources = []
        for f in sorted(os.listdir(MEDIA)):
            if f.lower().endswith((".mov", ".mp4", ".m4v")):
                _sources.append({"src": f, "duration": probe_duration(os.path.join(MEDIA, f))})
    return _sources


def level_worker():
    while True:
        try:
            for c in load()["tracks"]["video"]:
                key = f'{c["src"]}|{c["in"]:.3f}|{c["out"]:.3f}'
                if key not in levels and c["out"] > c["in"]:
                    levels[key] = export.auto_gain(MEDIA, c, os.path.join(PROJ, ".work"))
        except Exception: traceback.print_exc()
        threading.Event().wait(2)


def do_export(music):
    try:
        job.update(state="running", step="starting", k=0, n=0, out="", error="")
        out, total = export.render(PROJ, music=music, progress=lambda step, k, n: job.update(step=step, k=k, n=n))
        job.update(state="done", out=out)
    except Exception as e:
        job.update(state="error", error=str(e)); traceback.print_exc()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, body=b"", ctype="application/json", extra=None):
        if isinstance(body, (dict, list)): body = json.dumps(body).encode()
        if isinstance(body, str): body = body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)

    def file(self, path, ctype=None):
        size = os.path.getsize(path); ctype = ctype or mimetypes.guess_type(path)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and rng.startswith("bytes="):
            s, _, e = rng[6:].partition("-")
            start = int(s) if s else size - int(e); end = int(e) if (e and s) else size - 1
            end = min(end, start + CHUNK - 1, size - 1)  # serve open-ended ranges in chunks so stalled media never pins a connection
            self.send_response(206); self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype); self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1)); self.end_headers()
        with open(path, "rb") as f:
            f.seek(start); left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk: break
                try: self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError): return
                left -= len(chunk)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query); p = urllib.parse.unquote(u.path)
        if p == "/": return self.file(os.path.join(HERE, "index.html"), "text/html; charset=utf-8")
        if p == "/api/project": return self.send(200, load())
        if p == "/api/rev": return self.send(200, {"rev": load().get("rev", 0)})
        if p == "/api/sources": return self.send(200, sources())
        if p == "/api/levels": return self.send(200, levels)
        if p == "/api/export": return self.send(200, job)
        if p.startswith("/api/transcript/"):
            t = os.path.join(PROJ, "transcripts", os.path.splitext(os.path.basename(p))[0] + ".json")
            return self.send(200, open(t).read() if os.path.exists(t) else "[]")
        if p.startswith("/media/"):
            f = os.path.join(MEDIA, os.path.basename(p))
            if os.path.exists(f): return self.file(f, "video/mp4" if f.lower().endswith((".mov", ".mp4", ".m4v")) else None)
            return self.send(404, {"error": "not found"})
        if p == "/api/thumb":
            src = os.path.basename(q["src"][0]); t = float(q.get("t", ["0"])[0])
            name = hashlib.md5(f"{src}|{t:.2f}".encode()).hexdigest() + ".jpg"; out = os.path.join(THUMBS, name)
            if not os.path.exists(out):
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", os.path.join(MEDIA, src), "-frames:v", "1",
                                "-vf", "scale=90:160", out], capture_output=True)
            return self.file(out, "image/jpeg") if os.path.exists(out) else self.send(404)
        return self.send(404, {"error": "not found"})

    def do_PUT(self):
        if self.path != "/api/project": return self.send(404)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with lock:
            cur = load()
            if body.get("rev") != cur.get("rev"): return self.send(409, cur)
            body["rev"] = cur.get("rev", 0) + 1
            tmp = PJSON + ".tmp"; json.dump(body, open(tmp, "w"), indent=1); os.replace(tmp, PJSON)
        return self.send(200, {"rev": body["rev"]})

    def do_POST(self):
        if self.path.startswith("/api/export"):
            if job["state"] == "running": return self.send(409, job)
            music = "music=0" not in self.path
            threading.Thread(target=do_export, args=(music,), daemon=True).start()
            return self.send(200, {"ok": True})
        if self.path == "/api/reveal" and job.get("out"):
            subprocess.run(["open", "-R", job["out"]]); return self.send(200, {"ok": True})
        return self.send(404)


if __name__ == "__main__":
    threading.Thread(target=level_worker, daemon=True).start()
    print(f"EWVE on http://localhost:{PORT}  project: {PROJ}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
