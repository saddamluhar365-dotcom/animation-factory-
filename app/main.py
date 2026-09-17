from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .storage import load_config, save_config
from .providers import register
from .reference import analyze_reference, download_reference_url, save_reference_profile
from .pipeline import run_project

PROVIDERS = [("Gemini", "gemini"), ("Hugging Face", "huggingface"), ("Tavily", "tavily")]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Shorts Factory")
        self.geometry("1050x720")
        self.minsize(900, 620)
        self.config_data = load_config()
        self._build()
        self.after(200, self.first_run)

    def _build(self):
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="AI SHORTS FACTORY", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Button(top, text="Settings / APIs", command=self.api_window).pack(side="right")
        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status, padding=(14, 4)).pack(fill="x")

        main = ttk.Frame(self, padding=14)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="What should I create?").pack(anchor="w")
        self.prompt = tk.Text(main, height=10, wrap="word")
        self.prompt.pack(fill="x", pady=8)

        row = ttk.Frame(main)
        row.pack(fill="x", pady=5)
        ttk.Label(row, text="Duration (1–180 sec):").pack(side="left")
        self.duration = tk.IntVar(value=60)
        ttk.Spinbox(row, from_=1, to=180, textvariable=self.duration, width=8).pack(side="left", padx=8)
        ttk.Button(row, text="Generate Short", command=self.generate).pack(side="left", padx=12)
        ttk.Button(row, text="Reference Shorts", command=self.reference_setup).pack(side="left")

        self.log = tk.Text(main, height=16, state="disabled")
        self.log.pack(fill="both", expand=True, pady=12)

    def write_log(self, msg):
        self.after(
            0,
            lambda: (
                self.status.set(msg),
                self.log.configure(state="normal"),
                self.log.insert("end", msg + "\n"),
                self.log.see("end"),
                self.log.configure(state="disabled"),
            ),
        )

    def first_run(self):
        if not self.config_data.get("initialized"):
            self.api_window(first=True)

    def api_window(self, first=False):
        win = tk.Toplevel(self)
        win.title("API Configuration")
        win.geometry("820x650")
        win.transient(self)
        win.grab_set()

        ttk.Label(win, text="API Configuration", font=("Segoe UI", 16, "bold")).pack(pady=12)
        ttk.Label(
            win,
            text="Paste a key and press TEST & ADD. Every successful live key is stored; add as many keys as needed later.",
        ).pack(pady=4)

        frame = ttk.Frame(win, padding=15)
        frame.pack(fill="both", expand=True)

        for provider, label in PROVIDERS:
            box = ttk.LabelFrame(frame, text=provider, padding=10)
            box.pack(fill="x", pady=7)
            e = ttk.Entry(box, show="*", width=55)
            e.pack(side="left", fill="x", expand=True)
            result = ttk.Label(box, text=f"{len(load_config().get('apis', {}).get(label, []))} saved")
            result.pack(side="left", padx=8)
            ttk.Button(
                box,
                text="TEST & ADD",
                command=lambda p=label, e=e, r=result: self.test_api(p, e, r),
            ).pack(side="right")

        ttk.Label(
            win,
            text="First launch needs one working Gemini, Hugging Face and Tavily key. Settings can add more later.",
        ).pack(pady=6)
        ttk.Button(win, text="SAVE / CONTINUE", command=lambda: self.close_setup(win, first)).pack(pady=12)
        if first:
            win.protocol("WM_DELETE_WINDOW", lambda: None)

    def test_api(self, provider, entry, result):
        key = entry.get().strip()
        if not key:
            result.config(text="Enter key")
            return

        result.config(text="Testing...")

        def work():
            try:
                ok, msg = register(provider, key)
            except Exception as exc:
                ok, msg = False, str(exc)

            def done():
                if ok:
                    result.config(text=f"✓ LIVE ({len(load_config().get('apis', {}).get(provider, []))})")
                    self.write_log(f"{provider}: LIVE and auto-added — {msg}")
                else:
                    result.config(text="✗ FAILED")
                    self.write_log(f"{provider}: FAILED — {msg}")
                    if provider == "gemini":
                        messagebox.showerror("Gemini API test failed", msg)

            self.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def close_setup(self, win, first):
        cfg = load_config()
        missing = [p for _, p in PROVIDERS if not cfg.get("apis", {}).get(p)]
        if first and missing:
            messagebox.showwarning("Required APIs", "Add at least one working key for: " + ", ".join(missing))
            return
        if first:
            cfg["initialized"] = True
            save_config(cfg)
            win.destroy()
            self.write_log("Initial APIs configured.")
            self.after(300, self.reference_setup)
        else:
            win.destroy()
            self.write_log("API configuration saved.")

    def reference_setup(self):
        win = tk.Toplevel(self)
        win.title("Reference Shorts")
        win.geometry("720x430")
        win.transient(self)
        win.grab_set()
        ttk.Label(win, text="Reference Shorts — first-time style setup", font=("Segoe UI", 15, "bold")).pack(pady=12)
        ttk.Label(
            win,
            text="Paste Shorts links or upload downloaded Shorts. They are analyzed once and saved as a style profile.",
        ).pack(pady=4)

        url_box = ttk.Frame(win, padding=12)
        url_box.pack(fill="x")
        ttk.Label(url_box, text="Shorts URL:").pack(side="left")
        url_entry = ttk.Entry(url_box)
        url_entry.pack(side="left", fill="x", expand=True, padx=8)
        files = []

        def choose():
            selected = filedialog.askopenfilenames(
                title="Select reference Shorts",
                filetypes=[("Video", "*.mp4 *.mov *.mkv *.webm"), ("All", "*.*")],
            )
            files.extend(selected)
            count.config(text=f"{len(files)} file(s) selected")

        ttk.Button(
            url_box,
            text="Add URL",
            command=lambda: self._download_url(url_entry, count, files),
        ).pack(side="right")
        ttk.Button(win, text="Upload / Add Video Files", command=choose).pack(pady=10)
        count = ttk.Label(win, text="0 file(s) selected")
        count.pack()
        ttk.Button(win, text="ANALYZE REFERENCES", command=lambda: self._analyze_files(win, files)).pack(pady=20)
        ttk.Button(win, text="Skip for now", command=win.destroy).pack()

    def _download_url(self, entry, count, files):
        url = entry.get().strip()
        if not url:
            return
        self.write_log("Downloading reference Short...")

        def work():
            try:
                path = download_reference_url(url)
                files.append(str(path))
                self.after(0, lambda: count.config(text=f"{len(files)} file(s) selected"))
                self.write_log(f"Downloaded {path.name}")
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Download failed", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _analyze_files(self, win, files):
        if not files:
            messagebox.showwarning("References", "Add at least one reference Short.")
            return
        win.destroy()
        results = []
        for file_path in files:
            self.write_log(f"Analyzing {Path(file_path).name}...")
            results.append(analyze_reference(Path(file_path)))
        save_reference_profile(results)
        self.write_log("Reference profile saved. It will be reused on future generations.")

    def generate(self):
        instruction = self.prompt.get("1.0", "end").strip()
        if not instruction:
            messagebox.showwarning("Prompt", "Describe the Short first.")
            return
        duration = int(self.duration.get())

        def work():
            try:
                out = run_project(instruction, duration, self.write_log)
                self.after(0, lambda: messagebox.showinfo("Done", f"Video created:\n{out}"))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Generation failed", str(exc)))

        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
