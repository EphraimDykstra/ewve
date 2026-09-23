"""EWVE, Ephraim's Web Video Editor: local server.

  python server.py [project folder] [port]

With no folder, EWVE opens on the Projects screen, where you can pick a recent
project or drop videos in to start a new one. New projects live under
~/EWVE Projects (override with the EWVE_HOME environment variable).
"""
import json, os, sys, threading, subprocess, hashlib, urllib.parse, mimetypes, traceback, re, time, shutil, platform
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import export, ingest

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 5177
ROOT = os.path.abspath(os.path.expanduser(os.environ.get("EWVE_HOME", "~/EWVE Projects")))
RECENT = os.path.join(ROOT, ".recent.json")
CHUNK = 2 * 1024 * 1024
VIDEO_EXT = (".mov", ".mp4", ".m4v")
os.makedirs(ROOT, exist_ok=True)
lock = threading.Lock()


class Project:
    """Everything tied to the open project. Replaced wholesale when you switch."""
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.media = os.path.join(self.path, "Media")
        self.pjson = os.path.join(self.path, "project.json")
        self.work = os.path.join(self.path, ".work")
        self.thumbs = os.path.join(self.work, "thumbs"); os.makedirs(self.thumbs, exist_ok=True)
        self.levels_path = os.path.join(self.work, "levels.json")
        try: self.levels = json.load(open(self.levels_path))  # "src|in|out" -> auto gain dB, kept across restarts
        except Exception: self.levels = {}
        self._sources = None

    def load(self): return json.load(open(self.pjson))

    def sources(self):
        if self._sources is None:
            self._sources = [{"src": f, "duration": probe_duration(os.path.join(self.media, f))}
                             for f in sorted(os.listdir(self.media)) if f.lower().endswith(VIDEO_EXT)]
        return self._sources


cur = None  # the open Project, or None on the Projects screen
job = {"state": "idle", "step": "", "k": 0, "n": 0, "out": "", "error": ""}
ing = {"state": "idle", "project": "", "msg": "", "k": 0, "n": 0, "error": ""}


def probe_duration(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except ValueError: return 0.0


def recent():
    try: return [p for p in json.load(open(RECENT)) if os.path.exists(os.path.join(p, "project.json"))]
    except Exception: return []


def remember(path):
    r = [p for p in recent() if p != path]
    json.dump([path] + r[:49], open(RECENT, "w"), indent=1)


def open_project(path):
    global cur
    path = os.path.abspath(path)
    if not os.path.exists(os.path.join(path, "project.json")):
        if os.path.exists(os.path.join(path, "EWVE Project", "project.json")): path = os.path.join(path, "EWVE Project")
        else: raise FileNotFoundError(f"No EWVE project in {path}")
    cur = Project(path); remember(path)
    return cur


def safe_name(s):
    s = re.sub(r"[^\w\- .]", "", s).strip().strip(".")
    return s[:80] or time.strftime("Project %Y-%m-%d %H.%M")


def level_worker():
    while True:
        p = cur
        try:
            if p:
                for c in p.load()["tracks"]["video"]:
                    key = f'{c["src"]}|{c["in"]:.3f}|{c["out"]:.3f}'
                    if key not in p.levels and c["out"] > c["in"]:
                        p.levels[key] = export.auto_gain(p.media, c, p.work)
                        json.dump(p.levels, open(p.levels_path, "w"))
        except Exception: traceback.print_exc()
        threading.Event().wait(1)


def do_export(p, music):
    try:
        job.update(state="running", step="starting", k=0, n=0, out="", error="")
        out, total = export.render(p.path, music=music, progress=lambda step, k, n: job.update(step=step, k=k, n=n))
        job.update(state="done", out=out)
    except Exception as e:
        job.update(state="error", error=str(e)); traceback.print_exc()


def do_ingest(folder):
    try:
        ing.update(state="running", project=folder, msg="starting", k=0, n=0, error="")
        path = ingest.ingest(folder, progress=lambda msg, k, n: ing.update(msg=msg, k=k, n=n))
        ing.update(state="done", project=path)
    except BaseException as e:
        ing.update(state="error", error=str(e)); traceback.print_exc()


def reveal(path):
    sysname = platform.system()
    if sysname == "Darwin": subprocess.run(["open", "-R", path])
    elif sysname == "Windows": subprocess.run(["explorer", "/select,", path])
    elif shutil.which("xdg-open"): subprocess.run(["xdg-open", os.path.dirname(path)])


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    # --- local-only guard: any website could otherwise talk to this port ---
    def allowed(self, mutating):
        host = (self.headers.get("Host") or "").lower()
        if host not in (f"localhost:{PORT}", f"127.0.0.1:{PORT}"): return False      # blocks DNS rebinding
        if mutating:
            # Browsers always attach Origin to cross-site writes, so a localhost Origin proves the request came from the
            # editor page. Without an Origin (non-browser clients), require the X-EWVE header instead.
            origin = self.headers.get("Origin")
            if origin: return origin in (f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}")
            return self.headers.get("X-EWVE") == "1"
        return True

    def send(self, code, body=b"", ctype="application/json"):
        if isinstance(body, (dict, list)): body = json.dumps(body).encode()
        if isinstance(body, str): body = body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)

    def file(self, path, ctype=None):
        size = os.path.getsize(path); ctype = ctype or mimetypes.guess_type(path)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and rng.startswith("bytes="):
            s, _, e = rng[6:].partition("-")
            start = int(s) if s else size - int(e); end = int(e) if (e and s) else size - 1
            end = min(end, start + CHUNK - 1, size - 1)  # chunked so a stalled media request never pins a connection
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

    def body_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        if not self.allowed(False): return self.send(403, {"error": "forbidden"})
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query); p = urllib.parse.unquote(u.path)
        if p == "/": return self.file(os.path.join(HERE, "index.html"), "text/html; charset=utf-8")
        if p == "/api/home":
            projs = []
            for path in recent():
                try:
                    d = json.load(open(os.path.join(path, "project.json")))
                    projs.append({"path": path, "name": d.get("name") or os.path.basename(path), "clips": len(d["tracks"]["video"]),
                                  "modified": os.path.getmtime(os.path.join(path, "project.json"))})
                except Exception: pass
            return self.send(200, {"current": cur.path if cur else None, "root": ROOT, "projects": projs})
        if p == "/api/ingest": return self.send(200, ing)
        if p == "/api/export": return self.send(200, job)
        pr = cur
        if not pr: return self.send(409, {"error": "no project open"})
        if p == "/api/project": return self.send(200, pr.load())
        if p == "/api/rev": return self.send(200, {"rev": pr.load().get("rev", 0), "path": pr.path})
        if p == "/api/sources": return self.send(200, pr.sources())
        if p == "/api/levels": return self.send(200, pr.levels)
        if p.startswith("/api/transcript/"):
            t = os.path.join(pr.path, "transcripts", os.path.splitext(os.path.basename(p))[0] + ".json")
            return self.send(200, open(t).read() if os.path.exists(t) else "[]")
        if p.startswith("/media/"):
            f = os.path.join(pr.media, os.path.basename(p))
            if os.path.exists(f): return self.file(f, "video/mp4" if f.lower().endswith(VIDEO_EXT) else None)
            return self.send(404, {"error": "not found"})
        if p == "/api/thumb":
            src = os.path.basename(q["src"][0]); t = float(q.get("t", ["0"])[0])
            out = os.path.join(pr.thumbs, hashlib.md5(f"{src}|{t:.2f}".encode()).hexdigest() + ".jpg")
            if not os.path.exists(out):
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", os.path.join(pr.media, src), "-frames:v", "1",
                                "-vf", "scale=90:160:force_original_aspect_ratio=increase,crop=90:160", out], capture_output=True)
            return self.file(out, "image/jpeg") if os.path.exists(out) else self.send(404)
        return self.send(404, {"error": "not found"})

    def do_PUT(self):
        if not self.allowed(True): return self.send(403, {"error": "forbidden"})
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path == "/api/upload":  # raw body, one file per request, streamed to disk
            folder = os.path.join(ROOT, safe_name(q.get("project", [""])[0]))
            name = os.path.basename(q.get("file", [""])[0])
            if not name.lower().endswith(VIDEO_EXT): return self.send(400, {"error": "only .mov, .mp4 and .m4v files"})
            os.makedirs(folder, exist_ok=True)
            left = int(self.headers.get("Content-Length") or 0); tmp = os.path.join(folder, "." + name + ".part")
            with open(tmp, "wb") as f:
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk: break
                    f.write(chunk); left -= len(chunk)
            if left: os.remove(tmp); return self.send(400, {"error": "upload interrupted"})
            os.replace(tmp, os.path.join(folder, name))
            return self.send(200, {"ok": True, "folder": folder})
        pr = cur
        if u.path != "/api/project" or not pr: return self.send(404)
        body = self.body_json()
        with lock:
            now = pr.load()
            # A missing rev only comes from a tab whose earlier save was refused; accept it once rather than lose the edits.
            if "rev" in body and body.get("rev") != now.get("rev"): return self.send(409, now)
            body["rev"] = now.get("rev", 0) + 1
            tmp = pr.pjson + ".tmp"; json.dump(body, open(tmp, "w"), indent=1); os.replace(tmp, pr.pjson)
        return self.send(200, {"rev": body["rev"]})

    def do_POST(self):
        global cur
        if not self.allowed(True): return self.send(403, {"error": "forbidden"})
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/open":
            try: return self.send(200, {"path": open_project(self.body_json()["path"]).path})
            except Exception as e: return self.send(400, {"error": str(e)})
        if u.path == "/api/close":
            cur = None; return self.send(200, {"ok": True})
        if u.path == "/api/ingest":
            if ing["state"] == "running": return self.send(409, ing)
            folder = os.path.join(ROOT, safe_name(self.body_json().get("project", "")))
            if not os.path.isdir(folder): return self.send(400, {"error": "upload videos first"})
            threading.Thread(target=do_ingest, args=(folder,), daemon=True).start()
            return self.send(200, {"ok": True})
        if u.path == "/api/export":
            if not cur: return self.send(409, {"error": "no project open"})
            if job["state"] == "running": return self.send(409, job)
            threading.Thread(target=do_export, args=(cur, "music=0" not in self.path), daemon=True).start()
            return self.send(200, {"ok": True})
        if u.path == "/api/reveal" and job.get("out"):
            reveal(job["out"]); return self.send(200, {"ok": True})
        return self.send(404)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1]:
        open_project(sys.argv[1])
    threading.Thread(target=level_worker, daemon=True).start()
    print(f"EWVE on http://localhost:{PORT}  {'project: ' + cur.path if cur else 'projects: ' + ROOT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
