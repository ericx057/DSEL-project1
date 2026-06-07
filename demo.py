#!/usr/bin/env python3
"""DSEL Floating Island — Code Intelligence Demo for FreeCAD."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── Palette (GitHub Dark) ──────────────────────────────────────────────────
BG       = "#0d1117"
SURFACE  = "#161b22"
SURF2    = "#21262d"
BORDER   = "#30363d"
ACCENT   = "#58a6ff"
FG       = "#e6edf3"
FG2      = "#8b949e"
FG3      = "#6e7681"
GREEN    = "#3fb950"
RED_COL  = "#ff7b72"
USER_BG  = "#1c2128"
MONO     = "SF Mono"    if sys.platform == "darwin" else "Consolas"
SANS     = "SF Pro Text" if sys.platform == "darwin" else "Segoe UI"

DEMO_QUESTIONS = [
    "How does the Sketcher workbench propagate geometric constraint changes "
    "through the GCS solver, and which functions are called when a redundancy "
    "is detected?",
    "When a user saves a FreeCAD document containing a boolean cut operation, "
    "trace the full call chain from App::Document::save() through Part topology "
    "serialization to the final FCStd container format.",
]


# ── Retrieval engine ───────────────────────────────────────────────────────

class RetrievalEngine:
    def __init__(self, db_path: Optional[Path] = None):
        self._searcher = None
        self._reranker = None
        try:
            from src.retrieval.database import SQLiteUnifiedStore, HashingEmbeddingProvider
            from src.retrieval.hybrid import HybridSearcher
            from src.retrieval.reranker import LexicalReranker
            if db_path is None:
                db_path = ROOT / ".cis" / "index.db"
            store          = SQLiteUnifiedStore(db_path, HashingEmbeddingProvider())
            self._searcher = HybridSearcher(store, lambda_ratio=0.6)
            self._reranker = LexicalReranker()
        except Exception as exc:
            print(f"[demo] retrieval unavailable: {exc}", file=sys.stderr)

    @property
    def ready(self) -> bool:
        return self._searcher is not None

    def search(self, query: str, top_k: int = 8) -> List[Dict[str, Any]]:
        if not self.ready:
            return []
        hits = self._searcher.search(query, user_tier=1)
        return self._reranker.rerank(query, hits, top_m=top_k)

    def synthesize(self, query: str, hits: List[Dict[str, Any]]) -> str:
        if not hits:
            return (
                "No indexed artifacts matched this query.\n\n"
                "Index a repository first:\n"
                "  python -m src.ingestion.cli index <repo-path>"
            )
        lines = [f"Found {len(hits)} relevant artifact(s).\n"]
        for i, h in enumerate(hits[:6], 1):
            fp      = h.get("file_path", "")
            sym     = h.get("symbol_name") or ""
            kind    = h.get("kind", "chunk")
            lang    = h.get("language", "")
            ls, le  = h.get("line_start", 0), h.get("line_end", 0)
            text    = h.get("text", "")
            snippet = "\n    ".join(text.splitlines()[:4])
            loc     = f"  L{ls}–{le}" if ls else ""
            lines.append(f"{i}. {fp}{loc}")
            if sym:
                lines.append(f"   {sym}  [{kind}]  {lang}")
            if snippet:
                lines.append(f"   ···\n    {snippet}")
        lines.append("\nRanked by hybrid semantic + lexical score.")
        return "\n".join(lines)


# ── Scrollable frame ───────────────────────────────────────────────────────

class ScrollFrame(tk.Frame):
    def __init__(self, parent, bg: str, **kw):
        super().__init__(parent, bg=bg, **kw)
        self._c   = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self._vsb = tk.Scrollbar(self, orient="vertical", command=self._c.yview)
        self.inner = tk.Frame(self._c, bg=bg)
        self._win  = self._c.create_window((0, 0), window=self.inner, anchor="nw")
        self._c.configure(yscrollcommand=self._vsb.set)
        self._vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._c.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.inner.bind("<Configure>", lambda _: self._c.configure(
            scrollregion=self._c.bbox("all")))
        self._c.bind("<Configure>", lambda e: self._c.itemconfig(self._win, width=e.width))

    def scroll_bottom(self):
        self.after(60, lambda: self._c.yview_moveto(1.0))

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()


# ── Main application ───────────────────────────────────────────────────────

class DemoApp:
    W, H = 980, 620

    def __init__(self):
        self.engine          = RetrievalEngine()
        self._busy           = False
        self._loading_widget: Optional[tk.Widget] = None
        self._dx = self._dy  = 0

        self.root = tk.Tk()
        self.root.title("DSEL")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BORDER)
        if sys.platform == "darwin":
            self.root.attributes("-alpha", 0.97)

        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{self.W}x{self.H}+{(sw-self.W)//2}+{(sh-self.H)//2}")

        outer = tk.Frame(self.root, bg=BORDER, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)
        body = tk.Frame(outer, bg=BG)
        body.pack(fill=tk.BOTH, expand=True)

        self._build_titlebar(body)
        self._build_body(body)
        self._start_hotkey()
        self._post_assistant(
            "Welcome to DSEL — Code Intelligence for FreeCAD.\n\n"
            "I will retrieve the most relevant source artifacts for your question "
            "and show exactly which files were found.\n\n"
            "Suggested multihop questions:\n"
            + "\n".join(f"  {i+1}. {q}" for i, q in enumerate(DEMO_QUESTIONS))
        )
        if not self.engine.ready:
            self._post_assistant(
                "[Retrieval offline]  Index a repo first:\n"
                "  python -m src.ingestion.cli index <path-to-freecad>"
            )

    # ── title bar ──────────────────────────────────────────────────────────

    def _build_titlebar(self, parent):
        bar = tk.Frame(parent, bg=SURFACE, height=38)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
        bar.bind("<ButtonPress-1>", self._drag_start)
        bar.bind("<B1-Motion>",     self._drag_move)

        left = tk.Frame(bar, bg=SURFACE)
        left.pack(side=tk.LEFT, padx=14)
        for w in (left,):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>",     self._drag_move)

        def lbl(p, text, fg, font, side=tk.LEFT):
            l = tk.Label(p, text=text, fg=fg, bg=SURFACE, font=font)
            l.pack(side=side)
            l.bind("<ButtonPress-1>", self._drag_start)
            l.bind("<B1-Motion>",     self._drag_move)
            return l

        lbl(left, "◈ ", ACCENT,  (SANS, 14, "bold"))
        lbl(left, "DSEL",  FG,   (SANS, 12, "bold"))
        lbl(left, "  ·  Code Intelligence", FG3, (SANS, 10))
        status_color = GREEN if self.engine.ready else RED_COL
        lbl(left, "  ●", status_color, (SANS, 10))
        lbl(left, " indexed" if self.engine.ready else " offline", FG3, (SANS, 9))

        ctrl = tk.Frame(bar, bg=SURFACE)
        ctrl.pack(side=tk.RIGHT, padx=14)

        def btn(text, cmd, hover):
            b = tk.Label(ctrl, text=text, fg=FG2, bg=SURFACE,
                         font=(SANS, 15), cursor="hand2", padx=4)
            b.pack(side=tk.RIGHT)
            b.bind("<Button-1>", lambda _: cmd())
            b.bind("<Enter>",    lambda _: b.configure(fg=hover))
            b.bind("<Leave>",    lambda _: b.configure(fg=FG2))

        btn("×", self.root.quit,    RED_COL)
        btn("−", self.root.iconify, FG)
        tk.Frame(parent, bg=BORDER, height=1).pack(fill=tk.X)

    # ── two-panel body ─────────────────────────────────────────────────────

    def _build_body(self, parent):
        pane = tk.Frame(parent, bg=BG)
        pane.pack(fill=tk.BOTH, expand=True)

        # left: file list
        left = tk.Frame(pane, bg=SURFACE, width=290)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        lhdr = tk.Frame(left, bg=SURFACE, height=34)
        lhdr.pack(fill=tk.X)
        lhdr.pack_propagate(False)
        tk.Label(lhdr, text="Retrieved Files", fg=FG2, bg=SURFACE,
                 font=(SANS, 9, "bold")).pack(side=tk.LEFT, padx=12, pady=8)
        self._count_lbl = tk.Label(lhdr, text="", fg=ACCENT, bg=SURFACE,
                                   font=(SANS, 9))
        self._count_lbl.pack(side=tk.RIGHT, padx=12)
        tk.Frame(left, bg=BORDER, height=1).pack(fill=tk.X)
        self._files_sf = ScrollFrame(left, bg=SURFACE)
        self._files_sf.pack(fill=tk.BOTH, expand=True)
        tk.Label(self._files_sf.inner,
                 text="Ask a question to\nsee retrieved artifacts",
                 fg=FG3, bg=SURFACE, font=(SANS, 10), justify="center"
                 ).pack(pady=40)

        # divider
        tk.Frame(pane, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y)

        # right: chat
        right = tk.Frame(pane, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._chat_sf = ScrollFrame(right, bg=BG)
        self._chat_sf.pack(fill=tk.BOTH, expand=True)
        tk.Frame(right, bg=BORDER, height=1).pack(fill=tk.X)
        self._build_input(right)

    def _build_input(self, parent):
        area = tk.Frame(parent, bg=SURF2, padx=12, pady=10)
        area.pack(fill=tk.X)
        box = tk.Frame(area, bg=SURFACE)
        box.pack(fill=tk.X)

        self._inp = tk.Text(
            box, height=2, bg=SURFACE, fg=FG, font=(SANS, 11),
            relief="flat", bd=8, insertbackground=ACCENT,
            wrap=tk.WORD, selectbackground=ACCENT,
        )
        self._inp.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._inp.bind("<Return>",   self._on_enter)
        self._inp.bind("<FocusIn>",  self._inp_focus_in)
        self._inp.bind("<FocusOut>", self._inp_focus_out)
        self._inp.insert("1.0", self._PH)
        self._inp.configure(fg=FG3)

        send = tk.Button(
            box, text="↵", command=self._send,
            bg=ACCENT, fg="#000", font=(SANS, 13, "bold"),
            relief="flat", bd=0, padx=12, cursor="hand2",
            activebackground="#79c0ff", activeforeground="#000",
        )
        send.pack(side=tk.RIGHT, padx=(4, 0), pady=4)

        tk.Label(area, text="Return to send  ·  Shift+Return for newline  ·  Fn+⌘ to toggle",
                 fg=FG3, bg=SURF2, font=(SANS, 8)).pack(anchor="w", pady=(4, 0))

    _PH = "Ask anything about the codebase…"

    def _inp_focus_in(self, _):
        if self._inp.get("1.0", "end-1c") == self._PH:
            self._inp.delete("1.0", tk.END)
            self._inp.configure(fg=FG)

    def _inp_focus_out(self, _):
        if not self._inp.get("1.0", "end-1c").strip():
            self._inp.insert("1.0", self._PH)
            self._inp.configure(fg=FG3)

    def _on_enter(self, e):
        if not (e.state & 0x1):
            self._send()
            return "break"

    # ── send / retrieve ────────────────────────────────────────────────────

    def _send(self):
        raw = self._inp.get("1.0", "end-1c").strip()
        if not raw or raw == self._PH or self._busy:
            return
        self._inp.delete("1.0", tk.END)
        self._inp.insert("1.0", self._PH)
        self._inp.configure(fg=FG3)
        self._post_user(raw)
        self._busy = True
        self._loading_widget = self._post_assistant("Retrieving…", ephemeral=True)
        threading.Thread(target=self._worker, args=(raw,), daemon=True).start()

    def _worker(self, query: str):
        try:
            hits     = self.engine.search(query)
            response = self.engine.synthesize(query, hits)
            self.root.after(0, self._finish, hits, response)
        except Exception as exc:
            self.root.after(0, self._finish, [], f"Error: {exc}")

    def _finish(self, hits: List[Dict], response: str):
        self._busy = False
        if self._loading_widget and self._loading_widget.winfo_exists():
            self._loading_widget.destroy()
        self._post_assistant(response)
        self._render_files(hits)

    # ── chat bubbles ───────────────────────────────────────────────────────

    def _post_user(self, text: str) -> tk.Widget:
        return self._bubble(text, "user")

    def _post_assistant(self, text: str, ephemeral: bool = False) -> tk.Widget:
        return self._bubble(text, "assistant")

    def _bubble(self, text: str, role: str) -> tk.Widget:
        is_user = role == "user"
        wrap = tk.Frame(self._chat_sf.inner, bg=BG, padx=14, pady=4)
        wrap.pack(fill=tk.X, anchor="e" if is_user else "w")
        tk.Label(wrap, text="You" if is_user else "DSEL",
                 fg=ACCENT if is_user else FG2, bg=BG,
                 font=(SANS, 8, "bold")).pack(anchor="e" if is_user else "w")
        tk.Label(
            wrap, text=text,
            bg=USER_BG if is_user else SURFACE,
            fg=FG, font=(SANS, 11),
            wraplength=520, justify="left",
            anchor="w", padx=12, pady=8,
        ).pack(anchor="e" if is_user else "w", fill=None if is_user else tk.X)
        self._chat_sf.scroll_bottom()
        return wrap

    # ── files panel ────────────────────────────────────────────────────────

    def _render_files(self, hits: List[Dict]):
        self._files_sf.clear()
        self._count_lbl.configure(text=f"{len(hits)} found" if hits else "")
        if not hits:
            tk.Label(self._files_sf.inner, text="No results",
                     fg=FG3, bg=SURFACE, font=(SANS, 10)).pack(pady=20)
            return
        KIND = {"function": "ƒ", "class": "C", "method": "m", "module": "M", "chunk": "¶"}
        for idx, h in enumerate(hits):
            bg  = SURF2 if idx % 2 == 0 else SURFACE
            row = tk.Frame(self._files_sf.inner, bg=bg, pady=5, padx=10)
            row.pack(fill=tk.X, pady=1)
            fp   = h.get("file_path", "")
            sym  = h.get("symbol_name") or ""
            kind = h.get("kind", "chunk")
            lang = h.get("language", "")
            ls   = h.get("line_start", 0)
            le   = h.get("line_end", 0)
            parts = fp.split("/")
            short = "/".join(parts[-2:]) if len(parts) > 2 else fp
            top = tk.Frame(row, bg=bg)
            top.pack(fill=tk.X)
            tk.Label(top, text=KIND.get(kind, "·"), fg=ACCENT, bg=bg,
                     font=(MONO, 11, "bold")).pack(side=tk.LEFT)
            tk.Label(top, text=f" {short}", fg=FG, bg=bg,
                     font=(MONO, 9)).pack(side=tk.LEFT)
            if lang:
                tk.Label(top, text=lang, fg=FG3, bg=bg,
                         font=(SANS, 8)).pack(side=tk.RIGHT)
            detail = []
            if sym:
                detail.append(sym)
            if ls:
                detail.append(f"L{ls}–{le}")
            if detail:
                tk.Label(row, text="  ".join(detail), fg=FG2, bg=bg,
                         font=(MONO, 9)).pack(anchor="w")

    # ── drag ──────────────────────────────────────────────────────────────

    def _drag_start(self, e):
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root-self._dx}+{e.y_root-self._dy}")

    # ── global hotkey: Fn + ⌘ ─────────────────────────────────────────────

    def _start_hotkey(self):
        try:
            from pynput import keyboard
            held: set = set()

            def on_press(key):
                held.add(key)
                if {keyboard.Key.fn, keyboard.Key.cmd} <= held:
                    self.root.after(0, self._toggle)

            def on_release(key):
                held.discard(key)

            t = keyboard.Listener(on_press=on_press, on_release=on_release)
            t.daemon = True
            t.start()
        except Exception:
            pass

    def _toggle(self):
        if self.root.state() == "iconic":
            self.root.deiconify()
            self.root.lift()
        else:
            self.root.iconify()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    DemoApp().run()
