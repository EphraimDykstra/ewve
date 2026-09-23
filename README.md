# EWVE

Ephraim's Web Video Editor. A small, local, browser-based editor for vertical talking-head cuts: vox pops, supercuts, interview reels. Everything runs on your Mac. Your footage never leaves the folder it lives in.

It does a few things well:

- Lines up clips on a video track, with drag-to-reorder and drag-to-trim on the full source.
- Trims to the frame, by playhead, by number, or by clicking a word in the transcript.
- Auto-levels every clip to the same loudness, with a per-clip volume slider on top.
- Adds a music track that ducks under the voices on export.
- Exports a finished MP4 through ffmpeg, frame-exact and in sync.

The whole edit lives in one file, `project.json`. You can edit it in the browser, and Claude can edit the same file from a terminal. The browser picks up outside changes within about 2 seconds, and a revision counter stops either side from overwriting the other.

## Requirements

- macOS (uses `avconvert` to tone-map iPhone HDR footage to standard colour)
- `brew install ffmpeg whisper-cpp`
- Python 3

## Setup

```sh
cd ~/dev/ewve
python3 -m venv .venv && .venv/bin/pip install numpy
mkdir -p models && curl -L -o models/ggml-small.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin
```

## Use

```sh
./ewve "/path/to/folder of videos"
```

The first run on a folder creates `EWVE Project/` inside it, with converted media, transcripts and a starting `project.json` that has one clip per video. Later runs open that project again. You can also point `ewve` straight at an `EWVE Project` folder or at any folder that has a `project.json`.

Exports go to `EWVE Project/Exports/`.

### Keys

| Key | Action |
|---|---|
| Space | Play / pause |
| ← → | Step one frame (Shift for 10) |
| I / O | Trim the selected clip's in / out to the playhead |
| S | Split at the playhead |
| Delete | Remove the selected clip |
| ⌘Z / ⇧⌘Z | Undo / redo |

In the transcript, click a word to jump there in the source. Shift-click sets the in point, and Option-click sets the out point. Word times are approximate, so confirm cuts by ear.

## project.json

```json
{
  "rev": 12,
  "name": "My cut",
  "fps": 30, "width": 1080, "height": 1920,
  "tracks": {
    "video": [
      {"id": "c1", "src": "IMG_3288.mov", "in": 3.5667, "out": 4.8333, "section": "open", "gain_db": 0.0}
    ],
    "music": {"src": "Music bed.wav", "enabled": true, "gain_db": 0.0, "generated": true}
  },
  "end_hold": 1.0
}
```

- `src` is a file in `Media/`, and `in`/`out` are seconds in that file.
- `section` only colours the clip on the timeline: open, when, because or other.
- `gain_db` is added on top of automatic levelling.
- When `generated` is true, the music bed is composed at export time to fit the cut. When it's false, `src` in `Media/` is used.
- When editing by hand, keep `rev` as it is. The server bumps it.

## Files

| File | What it does |
|---|---|
| `ewve` | Launcher: sets up the folder if needed, starts the server, opens the browser |
| `ingest.py` | Folder of videos → `EWVE Project` (convert, transcribe, starting project) |
| `server.py` | Local HTTP server: UI, media with range requests, project API, thumbnails, export jobs |
| `export.py` | project.json → MP4 (frame-exact cuts, levelling, ducked music, loudness normalised) |
| `music.py` | Composes the soft four-chord music bed at any length |
| `index.html` | The editor UI |

## Ideas for later

- Claude inside the editor: "remove the ums", "find everyone who says X", "tighten every cut".
- Captions burned in from the transcripts.
- Title and text overlays.
- A second audio track for voice-over.
