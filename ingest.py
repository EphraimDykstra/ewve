"""Set up an EWVE project from a folder of videos.

  python ingest.py "<folder of videos>"

Creates "<folder>/EWVE Project/" with:
  Media/         1080p working copies. On macOS, iPhone HDR is tone-mapped to standard colour
                 with the built-in avconvert. Elsewhere ffmpeg makes a plain copy (HDR is not converted).
  transcripts/   word-level transcripts from whisper.cpp, used for click-to-cut (skipped if not installed)
  project.json   one clip per video, in filename order
Safe to re-run: existing media, transcripts and project.json are kept.
"""
import json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, "models", "ggml-small.en.bin")
VIDEO_EXT = (".mov", ".mp4", ".m4v")
WHISPER = shutil.which("whisper-cli") or shutil.which("whisper-cpp")


def probe(path, entries, stream=None):
    cmd = ["ffprobe", "-v", "error"] + (["-select_streams", stream] if stream else []) + ["-show_entries", entries, "-of", "csv=p=0", path]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip().split("\n")[0].strip(",")


def convert(src, out):
    if shutil.which("brctl"):  # macOS iCloud: make sure a cloud-only file is on disk first
        subprocess.run(["brctl", "download", src], capture_output=True)
    if shutil.which("avconvert"):
        r = subprocess.run(["avconvert", "-s", src, "-p", "Preset1920x1080", "-o", out, "--replace"], capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(out): return
    # portable fallback: 1080p H.264 at the source orientation
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-map", "0:v:0", "-map", "0:a:0?",
                    "-vf", "scale='if(gt(iw,ih),1920,-2)':'if(gt(iw,ih),-2,1920)'",
                    "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], check=True)


def transcribe(media_file, out_json, work):
    if not (WHISPER and os.path.exists(MODEL)): return False
    wav = os.path.join(work, "tx.wav"); stem = os.path.join(work, "tx")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", media_file, "-vn", "-ac", "1", "-ar", "16000", wav])
    subprocess.run([WHISPER, "-m", MODEL, "-f", wav, "-ml", "1", "-sow", "-oj", "-of", stem, "-np", "-t", "8"], capture_output=True)
    try:
        d = json.load(open(stem + ".json"))
        words = [{"w": s["text"].strip(), "t": round(s["offsets"]["from"] / 1000, 2)} for s in d["transcription"] if s["text"].strip()]
    except Exception:
        words = []
    json.dump(words, open(out_json, "w"))
    return True


def ingest(folder, progress=lambda msg, k, n: print(f"[{k}/{n}] {msg}", flush=True)):
    folder = os.path.abspath(folder)
    proj = os.path.join(folder, "EWVE Project")
    media, trans, work = (os.path.join(proj, d) for d in ("Media", "transcripts", ".work"))
    for d in (media, trans, work): os.makedirs(d, exist_ok=True)
    vids = sorted(f for f in os.listdir(folder) if f.lower().endswith(VIDEO_EXT) and not f.startswith("."))
    if not vids: raise RuntimeError(f"No videos found in {folder}")
    n = len(vids)
    for i, f in enumerate(vids, 1):
        base = os.path.splitext(f)[0]; out = os.path.join(media, base + ".mov")
        if not os.path.exists(out):
            progress(f"Converting {f}", i, n)
            convert(os.path.join(folder, f), out)
        tj = os.path.join(trans, base + ".json")
        if not os.path.exists(tj):
            progress(f"Transcribing {f}", i, n)
            transcribe(out, tj, work)
    pj = os.path.join(proj, "project.json")
    if not os.path.exists(pj):
        first = os.path.join(media, os.path.splitext(vids[0])[0] + ".mov")
        w, h = (int(v) for v in probe(first, "stream=width,height", "v:0").split(",")[:2])
        clips = []
        for k, f in enumerate(vids, 1):
            src = os.path.splitext(f)[0] + ".mov"
            d = float(probe(os.path.join(media, src), "format=duration") or 0)
            clips.append({"id": f"c{k}", "src": src, "in": 0.0, "out": round(int(d * 30) / 30, 4), "section": "", "gain_db": 0.0})
        json.dump({"rev": 1, "name": os.path.basename(folder), "fps": 30, "width": w, "height": h,
                   "tracks": {"video": clips, "music": {"src": "", "enabled": False, "gain_db": 0.0, "generated": True}},
                   "end_hold": 1.0}, open(pj, "w"), indent=1)
    progress("Ready", n, n)
    return proj


if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(__doc__)
    print("Project ready:", ingest(sys.argv[1]))
