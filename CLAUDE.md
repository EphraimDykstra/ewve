# Working on an EWVE project

These notes are for an AI assistant, such as Claude Code, helping someone edit a video in EWVE.

## The edit is one file

Each project lives in a folder named `EWVE Project` that holds:

- `project.json`, the edit itself. Edit this file.
- `Media/`, the editable copies of the source videos. Never modify these.
- `transcripts/<video name>.json`, word lists as `[{"w": "hello", "t": 1.23}, ...]`, where `t` is seconds from the start of that video. Times are approximate, to within about 0.3 seconds.
- `Exports/`, the finished MP4s.

The open editor polls the server about every 1.5 seconds and reloads when `project.json` changes, so the person sees your edits almost immediately.

## project.json

```json
{
  "rev": 7,
  "name": "My cut",
  "fps": 30, "width": 1080, "height": 1920,
  "tracks": {
    "video": [
      {"id": "c1", "src": "IMG_3288.mov", "in": 3.5667, "out": 4.8333,
       "section": "intro", "gain_db": 0.0,
       "crop": {"zoom": 1.0, "x": 0.0, "y": 0.0}}
    ],
    "music": {"src": "", "enabled": true, "gain_db": 0.0, "generated": true}
  },
  "end_hold": 1.0
}
```

- **Clips** play in array order. `src` names a file in `Media/`, and `in` and `out` are seconds in that file.
- **Frame alignment.** Keep `in` and `out` on frame boundaries, as multiples of 1/fps.
- **`section`** is a free-form tag that only colours the clip on the timeline.
- **`gain_db`** is added on top of automatic loudness levelling. Leave it at 0 unless asked.
- **`crop`** is optional. `zoom` is 1 or more. `x` and `y` run from -1 to 1, where -1 is the left or top edge and 1 is the right or bottom edge.
- **`width` and `height`** set the output format: 1080×1920 vertical, 1080×1350, 1080×1080 or 1920×1080.
- **Music.** When `generated` is true, a soft music bed is composed at export time. When it's false, the file named in `src` in `Media/` is used.
- **`rev`.** Never change `rev`. When you edit the file directly, write it back with `rev` unchanged. If the editor has saved since you read the file, re-read it and redo your change instead of overwriting.

## Doing a good job

- **Find cuts from the transcript,** then confirm them. Transcript times drift, so check a cut against the audio: measure loudness around the boundary with ffmpeg, or transcribe the trimmed piece again. A clean cut sits in the quiet gap between words.
- **Don't clip word endings.** Soft endings such as a final "s" or "fun" trail quietly. Leave about 0.1 seconds after the last loud frame.
- **Don't reorder or delete** clips the person didn't mention.
- **Say what you changed** in plain terms, such as "Clip 7 now starts on 'when I'm'," so the person can check it by ear.

## Running it

```sh
./ewve                       # Projects screen
./ewve "/path/to/videos"     # set up or open a folder
```

The server listens on http://localhost:5177, or the next free port. Its write endpoints require the header `X-EWVE: 1` and a localhost `Host`. Editing `project.json` on disk needs neither.
