"""Set up an EWVE project from a folder of videos.

  .venv/bin/python ingest.py "<folder of videos>"

Creates "<folder>/EWVE Project/" with:
  Media/         standard-colour 1080p copies (iPhone HDR is tone-mapped by macOS avconvert)
  transcripts/   word-level transcripts (whisper.cpp), used for click-to-cut
  project.json   one clip per video, in filename order
Safe to re-run: existing media, transcripts and project.json are kept.
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, "models", "ggml-small.en.bin")
VIDEO_EXT = (".mov", ".mp4", ".m4v")


def probe(path, entries, stream=None):
    cmd = ["ffprobe", "-v", "error"] + (["-select_streams", stream] if stream else []) + ["-show_entries", entries, "-of", "csv=p=0", path]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip().split("\n")[0].strip(",")


def ingest(folder):
    folder = os.path.abspath(folder)
    proj = os.path.join(folder, "EWVE Project")
    media, trans = os.path.join(proj, "Media"), os.path.join(proj, "transcripts")
    os.makedirs(media, exist_ok=True); os.makedirs(trans, exist_ok=True)
    vids = sorted(f for f in os.listdir(folder) if f.lower().endswith(VIDEO_EXT) and not f.startswith("."))
    if not vids: sys.exit(f"No videos found in {folder}")
    for i, f in enumerate(vids, 1):
        base = os.path.splitext(f)[0]; out = os.path.join(media, base + ".mov")
        if not os.path.exists(out):
            print(f"[{i}/{len(vids)}] converting {f}", flush=True)
            subprocess.run(["brctl", "download", os.path.join(folder, f)], capture_output=True)  # iCloud placeholders
            r = subprocess.run(["avconvert", "-s", os.path.join(folder, f), "-p", "Preset1920x1080", "-o", out, "--replace"], capture_output=True, text=True)
            if r.returncode or not os.path.exists(out):
                print(f"   avconvert failed ({r.stderr.strip()[:120]}), copying with ffmpeg instead")
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(folder, f), "-c:v", "libx264", "-crf", "18", "-c:a", "aac", out])
        tj = os.path.join(trans, base + ".json")
        if not os.path.exists(tj) and os.path.exists(MODEL):
            print(f"[{i}/{len(vids)}] transcribing {f}", flush=True)
            wav = os.path.join(proj, ".work", "tx.wav"); os.makedirs(os.path.dirname(wav), exist_ok=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", out, "-vn", "-ac", "1", "-ar", "16000", wav])
            stem = os.path.join(proj, ".work", "tx")
            subprocess.run(["whisper-cli", "-m", MODEL, "-f", wav, "-ml", "1", "-sow", "-oj", "-of", stem, "-np", "-t", "8"], capture_output=True)
            try:
                d = json.load(open(stem + ".json"))
                words = [{"w": s["text"].strip(), "t": round(s["offsets"]["from"] / 1000, 2)} for s in d["transcription"] if s["text"].strip()]
            except Exception:
                words = []
            json.dump(words, open(tj, "w"))
    pj = os.path.join(proj, "project.json")
    if not os.path.exists(pj):
        first = os.path.join(media, os.path.splitext(vids[0])[0] + ".mov")
        w, h = probe(first, "stream=width,height", "v:0").split(",")[:2]
        clips = []
        for n, f in enumerate(vids, 1):
            src = os.path.splitext(f)[0] + ".mov"
            d = float(probe(os.path.join(media, src), "format=duration") or 0)
            clips.append({"id": f"c{n}", "src": src, "in": 0.0, "out": round(int(d * 30) / 30, 4), "section": "other", "gain_db": 0.0})
        json.dump({"rev": 1, "name": os.path.basename(folder), "fps": 30, "width": int(w), "height": int(h),
                   "tracks": {"video": clips, "music": {"src": "", "enabled": False, "gain_db": 0.0, "generated": True}},
                   "end_hold": 1.0}, open(pj, "w"), indent=1)
    print(f"Project ready: {proj}")
    return proj


if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(__doc__)
    ingest(sys.argv[1])
