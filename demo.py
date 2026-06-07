#!/usr/bin/env python3
"""DSEL — Spotlight-style code intelligence demo for FreeCAD."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── Palette ────────────────────────────────────────────────────────────────────
BG      = "#1c1c1e"   # near-black, like macOS dark glass
PILL    = "#2c2c2e"   # search bar bg
BORDER  = "#3a3a3c"
ACCENT  = "#0a84ff"   # Apple blue
FG      = "#f5f5f7"
FG2     = "#aeaeb2"
FG3     = "#636366"
GREEN   = "#30d158"
RED_C   = "#ff453a"
DIVIDER = "#38383a"
RESULT  = "#232325"
MONO    = "SF Mono"    if sys.platform == "darwin" else "Consolas"
SANS    = "SF Pro Text" if sys.platform == "darwin" else "Segoe UI"

W_COLL  = 640          # collapsed width
H_COLL  = 56           # collapsed height
W_EXP   = 860          # expanded width
H_EXP   = 520          # expanded height
RADIUS  = 12           # visual corner radius (simulated via padding)

DEMO_Q = [
    "How does the Sketcher workbench propagate geometric constraint changes "
    "through the GCS solver, and which functions are called when a redundancy "
    "is detected?",
    "Trace the call from App::Document::save() through Part topology "
    "serialization to the final FCStd container format.",
]


# ── Retrieval engine ────────────────────────────────────────────────────────────

class RetrievalEngine:
    def __init__(self):
        self._searcher = None
        self._reranker = None
        try:
            from src.retrieval.database import SQLiteUnifiedStore, HashingEmbeddingProvider
            from src.retrieval.hybrid import HybridSearcher
            from src.retrieval.reranker import LexicalReranker
            db = ROOT / ".cis" / "index.db"
            store = SQLiteUnifiedStore(db, HashingEmbeddingProvider())
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


# ── App ─────────────────────────────────────────────────────────────────────────

class SpotlightDemo:
    def __init__(self):
        self.engine   = RetrievalEngine()
        self._busy    = False
        self._expanded = False
        self._dx = self._dy = 0

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.configure(bg=BORDER)
        if sys.platform == "darwin":
            self.root.attributes("-alpha", 0.96)

        # Center collapsed window
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = (sw - W_COLL) // 2
        y  = sh // 3          # slightly above center, like Spotlight
        self.root.geometry(f"{W_COLL}x{H_COLL}+{x}+{y}")

        # 1-px border frame
        outer = tk.Frame(self.root, bg=BORDER, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        self._main = tk.Frame(outer, bg=BG)
        self._main.pack(fill=tk.BOTH, expand=True)

        self._build_search_bar()
        self._build_results_panel()

        # Keyboard shortcuts
        self.root.bind("<Escape>", lambda _: self._collapse())
        self._entry.bind("<Return>",       lambda _: self._submit())
        self._entry.bind("<KP_Enter>",     lambda _: self._submit())
        self._entry.bind("<Shift-Return>", lambda e: "break")  # prevent submit on shift-return

        # Drag
        for w in (self._bar, self._icon_lbl, self._status_dot):
            w.bind("<ButtonPress-1>",  self._drag_start)
            w.bind("<B1-Motion>",      self._drag_move)

        self._entry.focus_set()

    # ── Search bar ──────────────────────────────────────────────────────────────

    def _build_search_bar(self):
        self._bar = tk.Frame(self._main, bg=BG, height=H_COLL)
        self._bar.pack(fill=tk.X)
        self._bar.pack_propagate(False)

        # Search icon
        self._icon_lbl = tk.Label(
            self._bar, text="⌕", fg=FG3, bg=BG,
            font=(SANS, 20), padx=14, cursor="fleur",
        )
        self._icon_lbl.pack(side=tk.LEFT)

        # Text entry — fills available space
        self._entry = tk.Entry(
            self._bar,
            bg=BG, fg=FG, insertbackground=FG,
            font=(SANS, 15),
            relief=tk.FLAT, bd=0,
            highlightthickness=0,
        )
        self._entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=10)
        self._set_placeholder()

        # Status dot + hint
        right = tk.Frame(self._bar, bg=BG)
        right.pack(side=tk.RIGHT, padx=14)
        dot_color = GREEN if self.engine.ready else RED_C
        self._status_dot = tk.Label(right, text="●", fg=dot_color, bg=BG, font=(SANS, 9))
        self._status_dot.pack(side=tk.LEFT)
        tk.Label(right, text=" esc", fg=FG3, bg=BG, font=(MONO, 10)).pack(side=tk.LEFT)

    def _set_placeholder(self):
        hint = DEMO_Q[0][:60] + "…"
        self._entry.delete(0, tk.END)
        self._entry.insert(0, hint)
        self._entry.configure(fg=FG3)
        self._entry.bind("<FocusIn>", self._clear_placeholder)

    def _clear_placeholder(self, _=None):
        if self._entry.cget("fg") == FG3:
            self._entry.delete(0, tk.END)
            self._entry.configure(fg=FG)
        self._entry.unbind("<FocusIn>")

    # ── Results panel (hidden until first query) ────────────────────────────────

    def _build_results_panel(self):
        # Divider
        self._divider = tk.Frame(self._main, bg=DIVIDER, height=1)

        # Two-column results area
        self._results_frame = tk.Frame(self._main, bg=BG)

        # Left: file list
        left = tk.Frame(self._results_frame, bg=BG, width=260)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=0)
        left.pack_propagate(False)

        tk.Label(left, text="RETRIEVED FILES", fg=FG3, bg=BG,
                 font=(SANS, 9, "bold"), anchor="w",
                 padx=14, pady=8).pack(fill=tk.X)

        file_scroll_outer = tk.Frame(left, bg=BG)
        file_scroll_outer.pack(fill=tk.BOTH, expand=True)
        self._file_canvas = tk.Canvas(file_scroll_outer, bg=BG,
                                       highlightthickness=0, bd=0)
        self._file_inner  = tk.Frame(self._file_canvas, bg=BG)
        win = self._file_canvas.create_window((0, 0), window=self._file_inner, anchor="nw")
        self._file_canvas.pack(fill=tk.BOTH, expand=True)
        self._file_inner.bind("<Configure>", lambda _: self._file_canvas.configure(
            scrollregion=self._file_canvas.bbox("all")))
        self._file_canvas.bind("<Configure>", lambda e:
            self._file_canvas.itemconfig(win, width=e.width))

        # Vertical divider
        tk.Frame(self._results_frame, bg=DIVIDER, width=1).pack(side=tk.LEFT, fill=tk.Y)

        # Right: response
        right = tk.Frame(self._results_frame, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(right, text="RESPONSE", fg=FG3, bg=BG,
                 font=(SANS, 9, "bold"), anchor="w",
                 padx=14, pady=8).pack(fill=tk.X)

        resp_outer = tk.Frame(right, bg=BG)
        resp_outer.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))
        self._resp_text = tk.Text(
            resp_outer,
            bg=BG, fg=FG2, font=(MONO, 11),
            relief=tk.FLAT, bd=0, highlightthickness=0,
            wrap=tk.WORD, state=tk.DISABLED,
            selectbackground=ACCENT,
        )
        vsb = tk.Scrollbar(resp_outer, orient="vertical",
                            command=self._resp_text.yview)
        self._resp_text.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._resp_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # ── Submit query ────────────────────────────────────────────────────────────

    def _submit(self):
        if self._busy:
            return
        self._clear_placeholder()
        query = self._entry.get().strip()
        if not query or self._entry.cget("fg") == FG3:
            return

        self._busy = True
        self._entry.configure(state=tk.DISABLED)
        self._expand()
        self._clear_files()
        self._set_response("Searching…")

        threading.Thread(target=self._worker, args=(query,), daemon=True).start()

    def _worker(self, query: str):
        hits = self.engine.search(query, top_k=8)
        self.root.after(0, self._finish, hits, query)

    def _finish(self, hits: List[Dict[str, Any]], query: str):
        self._render_files(hits)
        self._set_response(self._synthesize(hits))
        self._entry.configure(state=tk.NORMAL)
        self._busy = False

    # ── Expand / collapse ────────────────────────────────────────────────────────

    def _expand(self):
        if self._expanded:
            return
        self._expanded = True
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        # Shift window up so search bar stays at same position
        new_y = max(0, y - (H_EXP - H_COLL))
        self.root.geometry(f"{W_EXP}x{H_EXP}+{x}+{new_y}")
        self._divider.pack(fill=tk.X)
        self._results_frame.pack(fill=tk.BOTH, expand=True)

    def _collapse(self):
        if not self._expanded:
            self.root.quit()
            return
        self._expanded = False
        self._results_frame.pack_forget()
        self._divider.pack_forget()
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"{W_COLL}x{H_COLL}+{x}+{y}")
        self._entry.configure(state=tk.NORMAL)
        self._set_placeholder()

    # ── File list ─────────────────────────────────────────────────────────────────

    def _clear_files(self):
        for w in self._file_inner.winfo_children():
            w.destroy()

    KIND_ICON = {"function": "ƒ", "class": "C", "method": "m",
                 "module": "M", "chunk": "·"}

    def _render_files(self, hits: List[Dict[str, Any]]):
        self._clear_files()
        for h in hits:
            fp   = h.get("file_path", "")
            sym  = h.get("symbol_name") or ""
            kind = h.get("kind", "chunk")
            parts = fp.split("/")
            name  = parts[-1] if parts else fp
            parent = "/".join(parts[-3:-1]) if len(parts) > 2 else ""

            row = tk.Frame(self._file_inner, bg=BG, cursor="hand2")
            row.pack(fill=tk.X, padx=10, pady=2)

            icon = self.KIND_ICON.get(kind, "·")
            tk.Label(row, text=icon, fg=ACCENT, bg=BG,
                     font=(MONO, 11, "bold"), width=2).pack(side=tk.LEFT)
            info = tk.Frame(row, bg=BG)
            info.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(info, text=name, fg=FG, bg=BG,
                     font=(MONO, 10), anchor="w").pack(fill=tk.X)
            if parent:
                tk.Label(info, text=parent, fg=FG3, bg=BG,
                         font=(SANS, 9), anchor="w").pack(fill=tk.X)
            if sym:
                tk.Label(info, text=sym, fg=FG2, bg=BG,
                         font=(MONO, 9), anchor="w").pack(fill=tk.X)

    # ── Response ────────────────────────────────────────────────────────────────

    def _set_response(self, text: str):
        self._resp_text.configure(state=tk.NORMAL)
        self._resp_text.delete("1.0", tk.END)
        self._resp_text.insert(tk.END, text)
        self._resp_text.configure(state=tk.DISABLED)

    def _synthesize(self, hits: List[Dict[str, Any]]) -> str:
        if not hits:
            return (
                "No indexed artifacts matched.\n\n"
                "Build the corpus first:\n"
                "  python3 evaluation/build_freecad_corpus.py"
            )
        lines = [f"{len(hits)} artifact(s) retrieved.\n"]
        for i, h in enumerate(hits[:6], 1):
            fp   = h.get("file_path", "")
            sym  = h.get("symbol_name") or ""
            kind = h.get("kind", "chunk")
            text = h.get("text", "")
            snip = "\n  ".join(text.splitlines()[:4])
            ls, le = h.get("line_start", 0), h.get("line_end", 0)
            loc = f" L{ls}–{le}" if ls else ""
            lines.append(f"[{i}] {fp}{loc}")
            if sym:
                lines.append(f"    {sym}  [{kind}]")
            if snip:
                lines.append(f"  ···\n  {snip}")
            lines.append("")
        lines.append("Ranked by hybrid semantic + lexical score.")
        return "\n".join(lines)

    # ── Drag ─────────────────────────────────────────────────────────────────────

    def _drag_start(self, e):
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    # ── Run ──────────────────────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    SpotlightDemo().run()
