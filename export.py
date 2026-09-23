"""Render a project.json to a finished vertical MP4: frame-exact cuts, auto-levelled voices, optional ducked music bed."""
import json, os, re, subprocess, wave, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, ".venv", "bin", "python")
SR = 48000


def run(*a):
    subprocess.run(a, check=True, capture_output=True)


def lufs(path):
    out = subprocess.run(["ffmpeg", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", out)
    return float(m[-1]) if m else -70.0


def read_wav(path):
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def write_wav(path, x, ch=1):
    with wave.open(path, "wb") as w:
        w.setnchannels(ch); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


_level_cache = {}
def auto_gain(media, clip, work):
    """dB needed to bring this clip's cleaned speech to -18 LUFS (clamped). Cached per (src,in,out)."""
    key = (clip["src"], round(clip["in"], 3), round(clip["out"], 3))
    if key in _level_cache: return _level_cache[key]
    tmp = os.path.join(work, "lvl.wav")
    run("ffmpeg", "-v", "error", "-y", "-ss", f'{clip["in"]:.4f}', "-to", f'{clip["out"]:.4f}', "-i", os.path.join(media, clip["src"]),
        "-vn", "-ac", "1", "-ar", str(SR), "-af", "highpass=f=80,afftdn=nf=-25", tmp)
    g = float(np.clip(-18.0 - lufs(tmp), -12, 24))
    _level_cache[key] = g
    return g


def render(project_dir, music=True, progress=lambda *a: None):
    proj = json.load(open(os.path.join(project_dir, "project.json")))
    media = os.path.join(project_dir, "Media")
    work = os.path.join(project_dir, ".work"); os.makedirs(work, exist_ok=True)
    fps = proj.get("fps", 30); spf = SR // fps
    W, H = proj.get("width", 1080), proj.get("height", 1920)
    clips = [c for c in proj["tracks"]["video"] if c["out"] > c["in"]]
    end_hold = proj.get("end_hold", 1.0)
    voice, lst = [], open(os.path.join(work, "list.txt"), "w")
    for k, c in enumerate(clips):
        progress("clip", k + 1, len(clips))
        n = round((c["out"] - c["in"]) * fps); a0 = round(c["in"] * fps) / fps
        nh = round(end_hold * fps) if k == len(clips) - 1 else 0
        v = os.path.join(work, f"v{k:03d}.mp4")
        vf = f"fps={fps},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
        if nh: vf += f",tpad=stop_mode=clone:stop_duration={nh / fps:.4f}"
        run("ffmpeg", "-v", "error", "-y", "-ss", f"{a0:.4f}", "-i", os.path.join(media, c["src"]), "-an", "-vf", vf,
            "-frames:v", str(n + nh), "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", v)
        lst.write(f"file '{v}'\n")
        aw = os.path.join(work, f"a{k:03d}.wav")
        g = auto_gain(media, c, work) + float(c.get("gain_db", 0))
        run("ffmpeg", "-v", "error", "-y", "-ss", f"{a0:.4f}", "-i", os.path.join(media, c["src"]), "-vn", "-ac", "1", "-ar", str(SR),
            "-af", f"highpass=f=80,afftdn=nf=-25,volume={g:.2f}dB,alimiter=limit=0.89:level=false", "-t", f"{n / fps + 0.1:.4f}", aw)
        a = read_wav(aw)[: n * spf]; a = np.pad(a, (0, n * spf - len(a)))
        if len(a) > 1700: a[:240] *= np.linspace(0, 1, 240); a[-1440:] *= np.linspace(1, 0, 1440)
        voice += [a, np.zeros(nh * spf, np.float32)]
    lst.close()
    vo = np.concatenate(voice); total = len(vo) / SR
    write_wav(os.path.join(work, "voice.wav"), vo)
    progress("video", 0, 0)
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(work, "list.txt"), "-c", "copy", os.path.join(work, "cat.mp4"))
    run("ffmpeg", "-v", "error", "-y", "-i", os.path.join(work, "cat.mp4"), "-vf", f"fade=t=out:st={max(0, total - 1.2):.3f}:d=1.2",
        "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", os.path.join(work, "video.mp4"))
    progress("audio", 0, 0)
    m = proj["tracks"].get("music", {})
    outdir = os.path.join(project_dir, "Exports"); os.makedirs(outdir, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H.%M.%S")
    out = os.path.join(outdir, f'{proj.get("name", "Export")}{"" if music and m.get("enabled") else " (no music)"} {stamp}.mp4')
    if music and m.get("enabled"):
        bed = os.path.join(work, "bed.wav")
        if m.get("generated", True):
            run(PY, os.path.join(HERE, "music.py"), f"{total:.3f}", os.path.join(work, "bed_raw.wav"))
            src = os.path.join(work, "bed_raw.wav")
        else:
            src = os.path.join(media, m["src"])
        run("ffmpeg", "-v", "error", "-y", "-i", src, "-af", "highpass=f=40,lowpass=f=900", "-t", f"{total:.3f}", os.path.join(work, "bed_f.wav"))
        g = -40 - lufs(os.path.join(work, "bed_f.wav")) + float(m.get("gain_db", 0))
        run("ffmpeg", "-v", "error", "-y", "-i", os.path.join(work, "bed_f.wav"), "-af", f"volume={g:.2f}dB", bed)
        run("ffmpeg", "-v", "error", "-y", "-i", os.path.join(work, "video.mp4"), "-i", os.path.join(work, "voice.wav"), "-i", bed, "-filter_complex",
            "[1]aformat=channel_layouts=stereo,asplit[v][key];[2][key]sidechaincompress=threshold=0.008:ratio=12:attack=30:release=900:makeup=1[md];"
            "[v][md]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out)
    else:
        run("ffmpeg", "-v", "error", "-y", "-i", os.path.join(work, "video.mp4"), "-i", os.path.join(work, "voice.wav"), "-filter_complex",
            "[1]aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out)
    return out, total
