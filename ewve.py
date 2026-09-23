"""EWVE launcher.

  python ewve.py                 open the Projects screen (drop videos in to start)
  python ewve.py "<folder>"      open a folder: raw videos get set up, or an existing EWVE project opens
"""
import os, socket, subprocess, sys, threading, time, webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))


def free_port(start=5177):
    for p in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0: return p
    raise SystemExit("No free port found")


def main():
    folder = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else ""
    if folder:
        if not os.path.isdir(folder): raise SystemExit(f"Not a folder: {folder}")
        if not (os.path.exists(os.path.join(folder, "project.json")) or os.path.exists(os.path.join(folder, "EWVE Project", "project.json"))):
            sys.path.insert(0, HERE); import ingest
            folder = ingest.ingest(folder)
    port = free_port()
    threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(f"http://localhost:{port}")), daemon=True).start()
    subprocess.run([sys.executable, os.path.join(HERE, "server.py"), folder, str(port)])


if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: pass
