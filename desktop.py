"""Desktop launcher for the Mesopotamian Omen Analyzer.

Runs the Streamlit app under real CPython (so the eBL API fetch works — no browser
CORS, real sockets — and edits/imports persist to the real data/ folder) and shows it
in a native window via pywebview, instead of a browser tab.

    pip install -r requirements.txt        # includes streamlit-ace and pywebview
    python desktop.py

Streamlit is started on a private localhost port and the window points at it; closing
the window shuts Streamlit down.

NOTE: a distributable installer (PyInstaller .exe/.app, bundling CPython + Streamlit +
the streamlit-ace static assets) will be set up later — this launcher is the entry
point it will freeze.
"""
import os
import sys
import socket
import time
import subprocess
import urllib.request

import webview  # pywebview


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


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(here, "app.py")
    port = _free_port()
    url = f"http://127.0.0.1:{port}"

    cmd = [
        sys.executable, "-m", "streamlit", "run", app_path,
        "--server.port", str(port),
        "--server.address", "127.0.0.1",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
    ]
    # Run Streamlit from the repo root so its relative data/ paths resolve.
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
    main()
