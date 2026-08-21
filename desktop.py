"""Desktop launcher for the Mesopotamian Omen Analyzer.

Runs the Streamlit app under real CPython (so the eBL API fetch works — no browser
CORS, real sockets — and edits/imports persist to the real data/ folder) and shows it
in a native window via pywebview, instead of a browser tab.

    pip install -r requirements.txt        # includes streamlit-ace and pywebview
    python desktop.py

Streamlit is started on a private localhost port and the window points at it; closing
the window shuts Streamlit down.

This file is also the entry point of the frozen PyInstaller build (see
packaging/desktop_exe.spec). A frozen app has no separate Python interpreter to
spawn, so the window process re-launches its own exe with `--run-streamlit PORT`,
which starts the Streamlit server in-process; the bundled app.py, data/ and
references.bib live in the exe's _internal/ directory (sys._MEIPASS).
"""
import os
import sys
import socket
import time
import subprocess
import urllib.request

_FROZEN = getattr(sys, "frozen", False)


def _base_dir():
    """Folder holding app.py, data/, references.bib — _internal/ when frozen."""
    if _FROZEN:
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _free_port():
    """Pick an unused localhost port for the embedded Streamlit server."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_up(url, timeout=45):
    """Block until the Streamlit server answers, or give up after `timeout` s."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def _run_streamlit(port):
    """Run the Streamlit server in this process (the `--run-streamlit` child)."""
    here = _base_dir()
    os.chdir(here)  # app.py resolves data/ and references.bib relative to here
    sys.argv = [
        "streamlit", "run", os.path.join(here, "app.py"),
        "--server.port", str(port),
        "--server.address", "127.0.0.1",
        "--server.headless", "true",
        # No source watching in the frozen app; keep live-reload while developing.
        "--server.fileWatcherType", "none" if _FROZEN else "auto",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
    ]
    from streamlit.web import cli as stcli
    sys.exit(stcli.main())


def main():
    import webview  # pywebview; imported lazily so the server child skips it

    here = _base_dir()
    port = _free_port()
    url = f"http://127.0.0.1:{port}"

    # Frozen: the exe re-runs itself; dev: this file under the same interpreter.
    cmd = [sys.executable] + ([] if _FROZEN else [os.path.abspath(__file__)])
    cmd += ["--run-streamlit", str(port)]
    proc = subprocess.Popen(cmd, cwd=here)
    try:
        if not _wait_until_up(url):
            print("Streamlit did not start in time.", file=sys.stderr)
        webview.create_window("The Logogram Density Index (LDI)", url, width=1280, height=860)
        webview.start()                      # blocks until the window is closed
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if len(sys.argv) >= 3 and sys.argv[1] == "--run-streamlit":
        _run_streamlit(int(sys.argv[2]))
    else:
        main()
