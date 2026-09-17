from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .storage import load_config, save_config
from .providers import register
from .reference import analyze_reference, download_reference_url, save_reference_profile
from .pipeline import run_project
from .ui_dispatch import UiEventBridge
from core.db.memory import MemoryDB

PROVIDERS = [("Gemini", "gemini"), ("Hugging Face", "huggingface"), ("Tavily", "tavily")]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Shorts Factory")
        self.geometry("1050x720")
        self.minsize(900, 620)
        self.config_data = load_config()
        self._ui_events = UiEventBridge()
        self._reference_downloads: set[str] = set()
        self._build()
        self.after(50, self._drain_ui_events)
        self.after(200, self.first_run)

    def _drain_ui_events(self):
        try:
            self._ui_events.drain(limit=100)
        finally:
            if self.winfo_exists():
                self.after(50, self._drain_ui_events)

    def _post_ui(self, callback):
        self._ui_events.post(callback)

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
        ttk.Button(row, text="Channel Intelligence", command=self.channel_setup).pack(side="left", padx=8)

        mode_frame = ttk.LabelFrame(main, text="Video Provider", padding=(10, 6))
        mode_frame.pack(fill="x", pady=6)
        self.video_provider = tk.StringVar(value="image_animation")
        ttk.Radiobutton(
            mode_frame,
            text="Image → Animation (Hugging Face Image + 60 FPS FFmpeg Animation)",
            variable=self.video_provider,
            value="image_animation",
        ).pack(side="left", padx=10)
        ttk.Radiobutton(
            mode_frame,
            text="FAL Video (FAL Multi-Key Healthy Pool & Dynamic Video Models)",
            variable=self.video_provider,
            value="fal_video",
        ).pack(side="left", padx=10)

        self.log = tk.Text(main, height=14, state="disabled")
        self.log.pack(fill="both", expand=True, pady=10)

    def write_log(self, msg):
        def update():
            self.status.set(msg)
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")

        self._post_ui(update)

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
            box.pack(fill="x", pady=5)
            e = ttk.Entry(box, show="*", width=55)
            e.pack(side="left", fill="x", expand=True)
            result = ttk.Label(box, text=f"{len(load_config().get('apis', {}).get(label, []))} saved")
            result.pack(side="left", padx=8)
            ttk.Button(
                box,
                text="TEST & ADD",
                command=lambda p=label, e=e, r=result: self.test_api(p, e, r),
            ).pack(side="right")

        # Dedicated FAL Video API Pool Management
        fal_box = ttk.LabelFrame(frame, text="FAL Video API Pool (Unlimited Keys, Healthy Pool)", padding=10)
        fal_box.pack(fill="both", expand=True, pady=8)

        fal_input_row = ttk.Frame(fal_box)
        fal_input_row.pack(fill="x", pady=4)
        ttk.Label(fal_input_row, text="Add FAL Key:").pack(side="left", padx=4)
        fal_entry = ttk.Entry(fal_input_row, show="*", width=42)
        fal_entry.pack(side="left", fill="x", expand=True, padx=4)
        fal_add_lbl = ttk.Label(fal_input_row, text="")
        fal_add_lbl.pack(side="left", padx=6)
        ttk.Button(
            fal_input_row,
            text="TEST & ADD",
            command=lambda: self.test_and_add_fal_key(fal_entry, fal_add_lbl, refresh_fal_list),
        ).pack(side="right")

        fal_keys_container = ttk.Frame(fal_box)
        fal_keys_container.pack(fill="both", expand=True, pady=4)

        def refresh_fal_list():
            for child in fal_keys_container.winfo_children():
                child.destroy()
            from app.storage import get_keys_metadata, remove_key, toggle_key
            metadata = get_keys_metadata("fal")
            if not metadata:
                ttk.Label(
                    fal_keys_container,
                    text="No FAL keys configured. Add keys above to use FAL Video mode.",
                    font=("Segoe UI", 9, "italic"),
                ).pack(pady=4)
                return

            for item in metadata:
                row = ttk.Frame(fal_keys_container)
                row.pack(fill="x", pady=2)
                status_txt = "✓ Active" if item.get("status") == "active" and item.get("enabled") else f"[{item.get('status').upper()}]"
                ttk.Label(row, text=f"{item.get('label')}: {item.get('masked')}", width=36, anchor="w").pack(side="left", padx=4)
                ttk.Label(row, text=status_txt, width=14, anchor="w").pack(side="left", padx=4)

                raw_k = item.get("raw_key")
                ttk.Button(row, text="Test", width=6, command=lambda k=raw_k: self.test_single_fal_key(k, refresh_fal_list)).pack(side="left", padx=2)
                toggle_txt = "Disable" if item.get("enabled") else "Enable"
                new_state = not item.get("enabled")
                ttk.Button(row, text=toggle_txt, width=8, command=lambda k=raw_k, s=new_state: (toggle_key("fal", k, s), refresh_fal_list())).pack(side="left", padx=2)
                ttk.Button(row, text="Remove", width=8, command=lambda k=raw_k: (remove_key("fal", k), refresh_fal_list())).pack(side="left", padx=2)

        refresh_fal_list()

        ttk.Label(
            win,
            text="Required for launch: Gemini, Hugging Face, Tavily. FAL Video keys are optional for high-production mode.",
        ).pack(pady=6)
        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Channel Intelligence", command=self.channel_setup).pack(side="left", padx=8)
        ttk.Button(btn_frame, text="SAVE / CONTINUE", command=lambda: self.close_setup(win, first)).pack(side="left", padx=8)
        if first:
            win.protocol("WM_DELETE_WINDOW", lambda: None)

    def test_and_add_fal_key(self, entry, status_lbl, refresh_cb):
        key = entry.get().strip()
        if not key:
            status_lbl.config(text="Enter key")
            return
        status_lbl.config(text="Testing...")

        def work():
            from app.providers import test_fal
            from app.storage import add_key
            ok, msg = test_fal(key)
            if ok:
                add_key("fal", key)

            def done():
                try:
                    if status_lbl.winfo_exists():
                        status_lbl.config(text="✓ Added" if ok else "✗ Failed")
                    if ok:
                        entry.delete(0, "end")
                        refresh_cb()
                        self.write_log(f"FAL Key verified & added: {msg}")
                    else:
                        self.write_log(f"FAL Key verification failed: {msg}")
                        messagebox.showerror("FAL Key verification failed", msg)
                except Exception:
                    pass

            self._post_ui(done)

        threading.Thread(target=work, daemon=True).start()

    def test_single_fal_key(self, raw_key, refresh_cb):
        def work():
            from app.providers import test_fal
            from app.storage import update_key_status
            ok, msg = test_fal(raw_key)
            update_key_status("fal", raw_key, "active" if ok else "invalid")

            def done():
                refresh_cb()
                self.write_log(f"FAL Key health check: {'PASSED' if ok else 'FAILED'} - {msg}")

            self._post_ui(done)

        threading.Thread(target=work, daemon=True).start()


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
                try:
                    exists = result.winfo_exists()
                except Exception:
                    exists = False
                if exists:
                    if ok:
                        result.config(text=f"✓ LIVE ({len(load_config().get('apis', {}).get(provider, []))})")
                        try:
                            entry.delete(0, "end")
                        except Exception:
                            pass
                    else:
                        result.config(text="✗ FAILED")
                if ok:
                    self.write_log(f"{provider}: LIVE and auto-added — {msg}")
                else:
                    self.write_log(f"{provider}: FAILED — {msg}")
                    if provider == "gemini":
                        messagebox.showerror("Gemini API test failed", msg)

            self._post_ui(done)

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
        count = ttk.Label(win, text="0 file(s) selected")
        count.pack()

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
        ttk.Button(win, text="ANALYZE REFERENCES", command=lambda: self._analyze_files(win, files)).pack(pady=20)
        ttk.Button(win, text="Skip for now", command=win.destroy).pack()

    def _download_url(self, entry, count, files):
        url = entry.get().strip()
        if not url or url in self._reference_downloads:
            return
        self._reference_downloads.add(url)
        self.write_log("Downloading reference Short...")

        def work():
            try:
                path = download_reference_url(url)
            except Exception as exc:
                error_message = str(exc)
                self._post_ui(lambda error_message=error_message: messagebox.showerror("Download failed", error_message))
            else:
                def done():
                    files.append(str(path))
                    try:
                        if count.winfo_exists():
                            count.config(text=f"{len(files)} file(s) selected")
                    except Exception:
                        pass
                    self.write_log(f"Downloaded {path.name}")

                self._post_ui(done)
            finally:
                self._reference_downloads.discard(url)

        threading.Thread(target=work, daemon=True).start()

    def _analyze_files(self, win, files):
        if not files:
            messagebox.showwarning("References", "Add at least one reference Short.")
            return
        win.destroy()
        file_list = list(files)
        self.write_log(f"Analyzing {len(file_list)} reference Short(s)...")

        def work():
            try:
                results = []
                for file_path in file_list:
                    self.write_log(f"Analyzing {Path(file_path).name}...")
                    results.append(analyze_reference(Path(file_path)))
                save_reference_profile(results)
            except Exception as exc:
                error_message = str(exc)
                self._post_ui(lambda error_message=error_message: messagebox.showerror("Reference analysis failed", error_message))
            else:
                self.write_log("Reference profile saved. It will be reused on future generations.")

        threading.Thread(target=work, daemon=True).start()

    def channel_setup(self):
        win = tk.Toplevel(self)
        win.title("Channel Intelligence")
        win.geometry("820x680")
        win.transient(self)
        win.grab_set()

        ttk.Label(win, text="Permanent Channel Intelligence", font=("Segoe UI", 16, "bold")).pack(pady=12)
        ttk.Label(
            win,
            text="Connect your permanent YouTube channel handle. Shorts, recipes, and Channel DNA are automatically synchronized into PostgreSQL.",
        ).pack(pady=4)

        db = MemoryDB()
        active_prof = db.get_channel_profile() or {}

        # Handle entry & Connect button
        conn_frame = ttk.LabelFrame(win, text="YouTube Channel", padding=10)
        conn_frame.pack(fill="x", padx=15, pady=8)

        ttk.Label(conn_frame, text="Channel Handle / URL:").pack(side="left", padx=5)
        handle_var = tk.StringVar(value=active_prof.get("handle", ""))
        handle_entry = ttk.Entry(conn_frame, textvariable=handle_var, width=35)
        handle_entry.pack(side="left", padx=5)

        status_lbl = ttk.Label(conn_frame, text="Connected" if active_prof else "Not connected")
        status_lbl.pack(side="left", padx=10)

        # Stats Card
        stats_frame = ttk.LabelFrame(win, text="Channel Intelligence State", padding=10)
        stats_frame.pack(fill="x", padx=15, pady=8)

        stats_var = tk.StringVar()

        def refresh_stats():
            p = db.get_channel_profile()
            if not p:
                stats_var.set("No channel connected.")
                return
            stats = db.get_channel_stats(p["id"])
            dna_status = "Available" if stats["has_dna"] else "Pending"
            last_sync = stats["last_synced_at"] or "Never"
            analyzed_count = stats.get("analyzed_shorts_count", 0)
            stats_var.set(
                f"Channel: {stats['title']} ({stats['handle']})\n"
                f"Uploads Playlist: {stats['uploads_playlist_id'] or 'N/A'}\n"
                f"Videos: {stats['video_count']} | Shorts: {stats['shorts_count']} | Deep Analyzed: {analyzed_count}/10 | Recipes: {stats['recipe_count']}\n"
                f"Channel DNA: {dna_status} (10 Facets) | Last Synced: {last_sync}"
            )

        refresh_stats()
        ttk.Label(stats_frame, textvariable=stats_var, justify="left", font=("Consolas", 10)).pack(anchor="w")

        def connect():
            raw_h = handle_var.get().strip()
            if not raw_h:
                messagebox.showwarning("Channel", "Enter a YouTube handle or URL.")
                return
            status_lbl.config(text="Resolving...")

            def work():
                try:
                    from core.channel.resolver import ChannelResolver
                    resolver = ChannelResolver()
                    resolved = resolver.resolve(raw_h)
                    saved = db.save_channel_profile(resolved.to_dict())
                    def done():
                        status_lbl.config(text="✓ Connected")
                        refresh_stats()
                        self.write_log(f"Connected channel: {saved.get('title')} ({saved.get('handle')})")
                    self._post_ui(done)
                except Exception as exc:
                    self._post_ui(lambda e=str(exc): messagebox.showerror("Connection failed", e))

            threading.Thread(target=work, daemon=True).start()

        ttk.Button(conn_frame, text="SAVE / CONNECT HANDLE", command=connect).pack(side="right", padx=5)

        # Automation Toggles Frame
        toggles_frame = ttk.LabelFrame(win, text="Channel Intelligence Automation Toggles", padding=10)
        toggles_frame.pack(fill="x", padx=15, pady=8)

        auto_sync_var = tk.BooleanVar(value=bool(active_prof.get("auto_sync_enabled", True)))
        auto_analyze_var = tk.BooleanVar(value=bool(active_prof.get("auto_analyze_enabled", True)))
        auto_ref_var = tk.BooleanVar(value=bool(active_prof.get("auto_reference_enabled", True)))
        prevent_repeats_var = tk.BooleanVar(value=bool(active_prof.get("prevent_recipe_repeats", True)))

        def on_toggle_change():
            p = db.get_channel_profile()
            if p:
                db.update_channel_settings(
                    p["id"],
                    auto_sync_enabled=auto_sync_var.get(),
                    auto_analyze_enabled=auto_analyze_var.get(),
                    auto_reference_enabled=auto_ref_var.get(),
                    prevent_recipe_repeats=prevent_repeats_var.get(),
                )

        t_row1 = ttk.Frame(toggles_frame)
        t_row1.pack(fill="x", pady=2)
        ttk.Checkbutton(t_row1, text="Auto Sync", variable=auto_sync_var, command=on_toggle_change).pack(side="left", padx=12)
        ttk.Checkbutton(t_row1, text="Auto Analyze", variable=auto_analyze_var, command=on_toggle_change).pack(side="left", padx=12)
        ttk.Checkbutton(t_row1, text="Auto Reference Discovery", variable=auto_ref_var, command=on_toggle_change).pack(side="left", padx=12)
        ttk.Checkbutton(t_row1, text="Prevent Repeats", variable=prevent_repeats_var, command=on_toggle_change).pack(side="left", padx=12)

        # Actions frame
        actions_frame = ttk.LabelFrame(win, text="Intelligence Operations", padding=10)
        actions_frame.pack(fill="x", padx=15, pady=8)

        def sync_now():
            p = db.get_channel_profile()
            if not p:
                messagebox.showwarning("Channel", "Connect a channel first.")
                return
            self.write_log(f"Syncing videos for {p['handle']}...")

            def work():
                try:
                    from core.channel.sync import ChannelSyncEngine
                    syncer = ChannelSyncEngine(db)
                    res = syncer.sync_channel(p)
                    def done():
                        refresh_stats()
                        self.write_log(f"Sync completed: {res.videos_added} new videos added, {res.shorts_added} Shorts.")
                        messagebox.showinfo("Sync Complete", f"Discovered {res.videos_discovered} videos.\nAdded {res.videos_added} videos.")
                    self._post_ui(done)
                except Exception as exc:
                    self._post_ui(lambda e=str(exc): messagebox.showerror("Sync failed", e))

            threading.Thread(target=work, daemon=True).start()

        def deep_analyze_10():
            p = db.get_channel_profile()
            if not p:
                messagebox.showwarning("Channel", "Connect a channel first.")
                return
            self.write_log(f"Downloading & deeply decoding latest 10 Shorts for {p['handle']}...")

            def work():
                try:
                    from core.channel.deep_analyzer import ChannelDeepAnalyzer
                    analyzer = ChannelDeepAnalyzer(db)
                    res = analyzer.analyze_latest_shorts(p["id"], max_videos=10, status_cb=self.write_log)
                    def done():
                        refresh_stats()
                        self.write_log(f"Deep decode completed: {res.get('analyzed_count')} Shorts analyzed and Channel DNA updated in PostgreSQL.")
                        messagebox.showinfo(
                            "Deep Analysis Complete",
                            f"Successfully analyzed {res.get('analyzed_count')} Shorts.\n"
                            f"Permanent 10-facet Channel DNA saved in PostgreSQL."
                        )
                    self._post_ui(done)
                except Exception as exc:
                    self._post_ui(lambda e=str(exc): messagebox.showerror("Deep analysis failed", e))

            threading.Thread(target=work, daemon=True).start()

        def view_dna():
            p = db.get_channel_profile()
            if not p:
                messagebox.showwarning("Channel", "Connect a channel first.")
                return
            cdna = db.get_channel_dna(p["id"])
            if not cdna or not cdna.get("dna_profile"):
                messagebox.showinfo("Channel DNA", "Channel DNA is not computed yet. Click 'DEEP ANALYZE LATEST 10 SHORTS'.")
                return
            prof = cdna.get("dna_profile", {})
            style = prof.get("winning_style_dna", {}).get("signature", "Ready")
            cuisine = prof.get("dominant_cuisine", "Fusion")
            fps_val = prof.get("animation_dna", {}).get("target_fps", 60.0)
            pacing_txt = prof.get("pacing", "N/A")
            rules = "\n".join([f"  • {r}" for r in prof.get("quality_rules", [])[:4]])
            avoids = "\n".join([f"  • {a}" for a in prof.get("avoid_bad_patterns", [])[:4]])

            info_text = (
                f"CHANNEL DNA (10 Facets)\n"
                f"=====================================\n"
                f"• Winning Style: {style}\n"
                f"• Dominant Cuisine: {cuisine}\n"
                f"• Target Framerate: {fps_val} FPS (Cubic Easing)\n"
                f"• Pacing: {pacing_txt}\n\n"
                f"Quality Rules:\n{rules}\n\n"
                f"Avoid Patterns:\n{avoids}\n"
            )
            messagebox.showinfo("Channel DNA (PostgreSQL)", info_text)

        def view_recipes():
            p = db.get_channel_profile()
            if not p:
                messagebox.showwarning("Channel", "Connect a channel first.")
                return
            recs = db.get_recipes(p["id"])
            if not recs:
                messagebox.showinfo("Recipe Memory", "No recipes currently extracted. Click 'DEEP ANALYZE LATEST 10 SHORTS'.")
                return
            lines = [f"• {r['recipe_name']} ({r.get('cuisine', '')} - {r.get('primary_ingredient', '')})" for r in recs[:20]]
            messagebox.showinfo("Recipe Memory (Top 20)", "\n".join(lines))

        def view_signals():
            p = db.get_channel_profile()
            if not p:
                messagebox.showwarning("Channel", "Connect a channel first.")
                return
            signals = db.get_improvement_signals(p["id"])
            if not signals:
                messagebox.showinfo("Improvement Signals", "No signals recorded yet. Click 'DEEP ANALYZE LATEST 10 SHORTS'.")
                return
            lines = [f"[{s['area'].upper()}] {s['recommendation']}" for s in signals[:5]]
            messagebox.showinfo("Improvement Signals", "\n\n".join(lines))

        act_btn_row = ttk.Frame(actions_frame)
        act_btn_row.pack(fill="x", pady=4)
        ttk.Button(act_btn_row, text="SYNC NOW", command=sync_now).pack(side="left", padx=4)
        ttk.Button(act_btn_row, text="DEEP ANALYZE LATEST 10 SHORTS", command=deep_analyze_10).pack(side="left", padx=4)
        ttk.Button(act_btn_row, text="VIEW CHANNEL DNA", command=view_dna).pack(side="left", padx=4)
        ttk.Button(act_btn_row, text="RECIPE MEMORY", command=view_recipes).pack(side="left", padx=4)
        ttk.Button(act_btn_row, text="IMPROVEMENTS", command=view_signals).pack(side="left", padx=4)

        ttk.Button(win, text="CLOSE", command=win.destroy).pack(pady=15)

    def generate(self):
        instruction = self.prompt.get("1.0", "end").strip()
        db = MemoryDB()
        active_prof = db.get_channel_profile()

        if not instruction and not active_prof:
            messagebox.showwarning(
                "Channel Required",
                "A YouTube channel handle is required. Please open Settings → Channel Intelligence and connect your @channel_handle.",
            )
            return

        duration = int(self.duration.get())

        def work():
            try:
                provider = self.video_provider.get() if hasattr(self, "video_provider") else "image_animation"
                out = run_project(instruction, duration, self.write_log, video_provider=provider)
            except Exception as exc:
                error_message = str(exc)
                self._post_ui(lambda error_message=error_message: messagebox.showerror("Generation failed", error_message))
            else:
                self._post_ui(lambda out=out: messagebox.showinfo("Done", f"Video created:\n{out}"))

        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
