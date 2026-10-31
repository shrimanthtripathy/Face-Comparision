"""Desktop launcher (entry point of the packaged Windows app): starts Nodal on this computer and opens it.
Optionally shares Nodal with phones on the same Wi-Fi, so the Nodal Android app (or a phone browser) can connect to it."""
import os, secrets, socket, sys, threading, urllib.request, webbrowser
from pathlib import Path

SHARE_PORT = 8765

def free_port(preferred=0):
    """A free TCP port: the preferred one if it is available, otherwise any."""
    for p in ([preferred] if preferred else []) + [0]:
        s = socket.socket()
        try:
            s.bind(("", p)); return s.getsockname()[1]
        except OSError:
            pass
        finally:
            s.close()

def lan_ip():
    """This computer's address on the local network (what a phone must type)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1)); return s.getsockname()[0]
    except Exception:
        try: return socket.gethostbyname(socket.gethostname())
        except Exception: return "127.0.0.1"
    finally:
        s.close()

def main():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    appdata = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Nodal"; appdata.mkdir(parents=True, exist_ok=True)
    if getattr(sys, "frozen", False):  # windowed apps have no console: log to a file instead
        sys.stdout = sys.stderr = open(appdata / "nodal.log", "a", buffering=1)
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk(); root.title("Nodal"); root.geometry("400x300"); root.resizable(False, False)
    share = messagebox.askyesno("Nodal", "Let phones and tablets on your Wi-Fi use Nodal?\n\nYes: share on this Wi-Fi (an invitation code is shown).\nNo: this computer only.", parent=root)
    os.environ["NODAL_DATA_DIR"] = str(appdata)
    if (base / "models").exists(): os.environ["NODAL_MODEL_DIR"] = str(base / "models")
    if share:   # several people, each registers once with the invitation code
        code = f"{secrets.randbelow(10 ** 6):06d}"; port = free_port(SHARE_PORT); host = "0.0.0.0"
        os.environ.update({"NODAL_MODE": "hosted", "NODAL_INVITE_CODE": code})
        url = f"http://127.0.0.1:{port}/"; phone = f"{lan_ip()}:{port}"
    else:       # single user on this computer only; nothing else on the network can reach it
        token = secrets.token_hex(16); port = free_port(); host = "127.0.0.1"
        os.environ.update({"NODAL_MODE": "desktop", "NODAL_LOCAL_TOKEN": token})
        url = f"http://127.0.0.1:{port}/?t={token}"; code = phone = None
    import uvicorn
    from backend.main import app
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning", loop="asyncio", http="h11", ws="none"))
    threading.Thread(target=server.run, daemon=True).start()

    msg = tk.Label(root, text="Starting Nodal (loading face models)...", pady=10); msg.pack()
    if share:
        tk.Label(root, text=f"On your phone enter:  {phone}\nInvitation code:  {code}", font=("Segoe UI", 11, "bold"), justify="left").pack(pady=4)
        def copy(): root.clipboard_clear(); root.clipboard_append(phone)
        tk.Button(root, text="Copy phone address", command=copy).pack(pady=2)
        tk.Label(root, text="If Windows asks, allow Nodal on private networks. Use this only on a Wi-Fi network you trust.",
                 fg="#5B6B76", wraplength=360, justify="left").pack(pady=4)
    tk.Button(root, text="Open Nodal in browser", command=lambda: webbrowser.open(url)).pack(pady=4)
    tk.Button(root, text="Quit Nodal", command=root.destroy).pack(pady=4)
    state = {"opened": False}
    def poll():
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1).read()
            if not state["opened"]:
                state["opened"] = True; msg.config(text="Nodal is running. Keep this window open while you work."); webbrowser.open(url)
        except Exception: pass
        root.after(1500, poll)
    root.after(500, poll); root.mainloop(); server.should_exit = True

if __name__ == "__main__": main()
