# EWVE

**Ephraim's Web Video Editor.** A free, simple video editor that runs in your browser, on your own computer. It's built for short talking-head edits: vox pops, supercuts, interview reels, and clips for LinkedIn, Instagram or TikTok.

Your footage never leaves your machine. There's no account, no upload and no watermark.

## What it does

- **Drop in videos** or a whole folder. EWVE makes editable copies and transcribes them.
- **Line up clips** on a timeline. Drag to reorder, and drag an edge to trim.
- **Cut on the word.** Click any word in a clip's transcript to jump there. Shift-click sets the in point, and Option-click sets the out point.
- **Frame for any format.** Choose vertical 9:16, portrait 4:5, square or landscape. Zoom and reposition each clip, so a wide shot works in a vertical video.
- **Even out the audio.** Every clip is levelled automatically, with a volume slider per clip on top.
- **Add a music bed** that dips under the voices.
- **Export an MP4** with frame-accurate cuts, ready to post.

## Works with Claude

The whole edit is one file, `EWVE Project/project.json`. Claude can edit it directly, from Claude Code in a terminal next to your browser, and the editor picks up the change within about 2 seconds. You can also have Claude in Chrome drive the editor itself. See [CLAUDE.md](CLAUDE.md) for the format and the rules an assistant should follow.

Things to ask for:

- "Remove every 'um' at the start of a clip."
- "Put every answer that mentions friends first."
- "Tighten every cut to start on the first word."
- "Lower clip 12 by 3 dB."

## Requirements

- **macOS** is the main platform. It uses macOS's built-in `avconvert` to convert iPhone HDR footage to standard colour, so it looks right when posted.
- **Linux and Windows** should work, but they haven't been tested much. Video is copied with ffmpeg instead, and HDR footage is not colour-converted.
- Python 3.10 or newer, [ffmpeg](https://ffmpeg.org), and, for transcripts, [whisper.cpp](https://github.com/ggml-org/whisper.cpp).

## Install

```sh
git clone https://github.com/EphraimDykstra/ewve.git
cd ewve
./setup.sh
```

`setup.sh` installs ffmpeg and whisper.cpp through Homebrew if they're missing. It then creates a Python environment and downloads the English transcription model, about 470 MB. To skip transcripts, run `SKIP_TRANSCRIPTS=1 ./setup.sh`.

On Windows, install Python, ffmpeg and, optionally, whisper.cpp yourself, then run:

```bat
python -m venv .venv
.venv\Scripts\pip install numpy
.venv\Scripts\python ewve.py
```

## Use

```sh
./ewve
```

Your browser opens on the Projects screen. Drop videos in, name the project, and click **Create project**. New projects are saved in `~/EWVE Projects` by default. To use another location, set the `EWVE_HOME` environment variable.

You can also point EWVE straight at a folder. A folder of raw videos gets set up in place, and a folder that already has a project opens directly:

```sh
./ewve "/path/to/videos"
```

Exports are saved to `EWVE Project/Exports/`.

### Keys

| Key | Action |
|---|---|
| Space | Play or pause |
| ← → | Step one frame (Shift steps 10) |
| I / O | Trim the selected clip's start or end to the playhead |
| S | Split at the playhead |
| Delete | Remove the selected clip |
| ⌘Z / ⇧⌘Z | Undo / redo |

## How it works

| File | Role |
|---|---|
| `ewve` / `ewve.py` | Launcher. Sets up a folder if needed, starts the server and opens the browser. |
| `server.py` | Local web server on `localhost` only. Serves the editor, video with seeking, the project API, thumbnails and background jobs. |
| `ingest.py` | Turns a folder of videos into an `EWVE Project`: converts the video, transcribes it and writes a starting `project.json`. |
| `export.py` | Renders `project.json` to an MP4 with frame-exact cuts, levelled voices, framing, the ducked music bed and loudness normalisation. |
| `music.py` | Composes a soft, royalty-free music bed at any length. |
| `index.html` | The editor, as a single page with no build step. |

The server only answers the editor's own page. It rejects requests from other websites and from non-local addresses, so a site you visit can't send commands to your EWVE.

## License

MIT. Use it, change it, share it.
