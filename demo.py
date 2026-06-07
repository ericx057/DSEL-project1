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
BG      = "#1c1c1e"
PILL    = "#2c2c2e"
BORDER  = "#3a3a3c"
ACCENT  = "#0a84ff"
FG      = "#f5f5f7"
FG2     = "#aeaeb2"
FG3     = "#636366"
GREEN   = "#30d158"
RED_C   = "#ff453a"
DIVIDER = "#38383a"
MONO    = "SF Mono"     if sys.platform == "darwin" else "Consolas"
SANS    = "SF Pro Text" if sys.platform == "darwin" else "Segoe UI"

W_COLL  = 660
H_COLL  = 58
W_EXP   = 880
H_EXP   = 540
ANIM_MS = 260           # expand animation duration

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
    def __init__(self, auto_query: Optional[str] = None):
        self.engine      = RetrievalEngine()
        self._busy       = False
        self._expanded   = False
        self._anim_step  = 0
        self._dx = self._dy = 0

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.configure(bg=BORDER)
        if sys.platform == "darwin":
            self.root.attributes("-alpha", 0.96)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = (sw - W_COLL) // 2
        y  = sh // 3
        self.root.geometry(f"{W_COLL}x{H_COLL}+{x}+{y}")
        self._origin_x = x
        self._origin_y = y

        outer = tk.Frame(self.root, bg=BORDER, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)
        self._main = tk.Frame(outer, bg=BG)
        self._main.pack(fill=tk.BOTH, expand=True)

        self._build_search_bar()
        self._build_results_panel()

        self.root.bind("<Escape>", lambda _: self._collapse())
        self._entry.bind("<Return>",   lambda _: self._submit())
        self._entry.bind("<KP_Enter>", lambda _: self._submit())

        for w in (self._bar, self._icon_lbl, self._status_dot):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>",     self._drag_move)

        self._entry.focus_set()

        if auto_query:
            self.root.after(400, lambda: self._fire(auto_query))

    # ── Search bar ──────────────────────────────────────────────────────────────

    def _build_search_bar(self):
        self._bar = tk.Frame(self._main, bg=BG, height=H_COLL)
        self._bar.pack(fill=tk.X)
        self._bar.pack_propagate(False)

        self._icon_lbl = tk.Label(
            self._bar, text="⌕", fg=FG3, bg=BG,
            font=(SANS, 20), padx=14, cursor="fleur",
        )
        self._icon_lbl.pack(side=tk.LEFT)

        self._entry = tk.Entry(
            self._bar, bg=BG, fg=FG, insertbackground=ACCENT,
            font=(SANS, 15), relief=tk.FLAT, bd=0, highlightthickness=0,
        )
        self._entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=10)
        self._set_placeholder()

        right = tk.Frame(self._bar, bg=BG)
        right.pack(side=tk.RIGHT, padx=14)
        dot_color = GREEN if self.engine.ready else RED_C
        self._status_dot = tk.Label(right, text="●", fg=dot_color, bg=BG, font=(SANS, 9))
        self._status_dot.pack(side=tk.LEFT)
        tk.Label(right, text="  esc", fg=FG3, bg=BG, font=(MONO, 10)).pack(side=tk.LEFT)

    def _set_placeholder(self):
        short = DEMO_Q[0][:62] + "…"
        self._entry.delete(0, tk.END)
        self._entry.insert(0, short)
        self._entry.configure(fg=FG3)
        self._entry.bind("<FocusIn>", self._clear_placeholder)

    def _clear_placeholder(self, _=None):
        if self._entry.cget("fg") == FG3:
            self._entry.delete(0, tk.END)
            self._entry.configure(fg=FG)
        self._entry.unbind("<FocusIn>")

    # ── Results panel ───────────────────────────────────────────────────────────

    def _build_results_panel(self):
        self._divider = tk.Frame(self._main, bg=DIVIDER, height=1)

        self._results_frame = tk.Frame(self._main, bg=BG)

        # ── Left: file list ──────────────────────────────────────────────────
        left = tk.Frame(self._results_frame, bg=BG, width=270)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        hdr_l = tk.Frame(left, bg=BG)
        hdr_l.pack(fill=tk.X, padx=14, pady=(10, 6))
        tk.Label(hdr_l, text="RETRIEVED FILES", fg=FG3, bg=BG,
                 font=(SANS, 9, "bold")).pack(side=tk.LEFT)
        self._file_count = tk.Label(hdr_l, text="", fg=ACCENT, bg=BG,
                                     font=(MONO, 9))
        self._file_count.pack(side=tk.LEFT, padx=6)

        fc_outer = tk.Frame(left, bg=BG)
        fc_outer.pack(fill=tk.BOTH, expand=True)
        self._fc = tk.Canvas(fc_outer, bg=BG, highlightthickness=0, bd=0)
        self._fi = tk.Frame(self._fc, bg=BG)
        win = self._fc.create_window((0, 0), window=self._fi, anchor="nw")
        self._fc.pack(fill=tk.BOTH, expand=True)
        self._fi.bind("<Configure>", lambda _: self._fc.configure(
            scrollregion=self._fc.bbox("all")))
        self._fc.bind("<Configure>", lambda e:
            self._fc.itemconfig(win, width=e.width))
        self._bind_scroll(self._fc)

        # ── Vertical divider ─────────────────────────────────────────────────
        tk.Frame(self._results_frame, bg=DIVIDER, width=1).pack(
            side=tk.LEFT, fill=tk.Y)

        # ── Right: response ──────────────────────────────────────────────────
        right = tk.Frame(self._results_frame, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        hdr_r = tk.Frame(right, bg=BG)
        hdr_r.pack(fill=tk.X, padx=14, pady=(10, 6))
        tk.Label(hdr_r, text="RESPONSE", fg=FG3, bg=BG,
                 font=(SANS, 9, "bold")).pack(side=tk.LEFT)

        resp_outer = tk.Frame(right, bg=BG)
        resp_outer.pack(fill=tk.BOTH, expand=True, padx=(14, 4), pady=(0, 14))
        vsb = tk.Scrollbar(resp_outer, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._resp = tk.Text(
            resp_outer, bg=BG, fg=FG2, font=(MONO, 11),
            relief=tk.FLAT, bd=0, highlightthickness=0,
            wrap=tk.WORD, state=tk.DISABLED,
            selectbackground=ACCENT,
            yscrollcommand=vsb.set,
            spacing1=2, spacing3=2,
        )
        vsb.configure(command=self._resp.yview)
        self._resp.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._bind_scroll(self._resp)

    def _bind_scroll(self, widget):
        widget.bind("<MouseWheel>", lambda e: widget.yview_scroll(
            int(-1 * (e.delta / 120)), "units"))

    # ── Submit ──────────────────────────────────────────────────────────────────

    def _submit(self):
        if self._busy:
            return
        self._clear_placeholder()
        query = self._entry.get().strip()
        if not query or self._entry.cget("fg") == FG3:
            return
        self._fire(query)

    def _fire(self, query: str):
        if self._busy:
            return
        self._busy = True
        # Show placeholder text in entry if firing programmatically
        if self._entry.get() != query:
            self._entry.configure(fg=FG)
            self._entry.delete(0, tk.END)
            self._entry.insert(0, query)
        self._entry.configure(state=tk.DISABLED)
        self._clear_files()
        self._write_response("Searching…")
        self._begin_expand()
        threading.Thread(target=self._worker, args=(query,), daemon=True).start()

    def _worker(self, query: str):
        hits = self.engine.search(query, top_k=8)
        self.root.after(0, self._finish, hits)

    def _finish(self, hits: List[Dict[str, Any]]):
        self._render_files(hits)
        self._write_response(self._synthesize(hits))
        self._entry.configure(state=tk.NORMAL)
        self._busy = False

    # ── Expand animation (grows DOWN from the search bar) ──────────────────────

    def _begin_expand(self):
        if self._expanded:
            return
        self._expanded = True
        # Pack results first (invisible until window is tall enough)
        self._divider.pack(fill=tk.X)
        self._results_frame.pack(fill=tk.BOTH, expand=True)
        self._anim_frame = 0
        self._anim_frames = max(1, ANIM_MS // 16)
        self._anim_start_w = self.root.winfo_width()
        self._anim_start_h = self.root.winfo_height()
        self._anim_x = self.root.winfo_x()
        self._anim_y = self.root.winfo_y()
        self.root.after(16, self._anim_tick)

    def _anim_tick(self):
        self._anim_frame += 1
        t = self._anim_frame / self._anim_frames
        # ease-out cubic
        t_e = 1 - (1 - t) ** 3
        w = int(self._anim_start_w + (W_EXP - self._anim_start_w) * t_e)
        h = int(self._anim_start_h + (H_EXP - self._anim_start_h) * t_e)
        # Centre horizontally as width grows; y stays fixed (expands downward)
        new_x = self._anim_x - (w - self._anim_start_w) // 2
        self.root.geometry(f"{w}x{h}+{new_x}+{self._anim_y}")
        if self._anim_frame < self._anim_frames:
            self.root.after(16, self._anim_tick)

    def _collapse(self):
        if not self._expanded:
            self.root.quit()
            return
        self._expanded = False
        self._results_frame.pack_forget()
        self._divider.pack_forget()
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        # Re-centre width
        new_x = x + (self.root.winfo_width() - W_COLL) // 2
        self.root.geometry(f"{W_COLL}x{H_COLL}+{new_x}+{y}")
        self._entry.configure(state=tk.NORMAL)
        self._set_placeholder()

    # ── File list ───────────────────────────────────────────────────────────────

    def _clear_files(self):
        for w in self._fi.winfo_children():
            w.destroy()
        self._file_count.configure(text="")

    KIND = {"function": "ƒ", "class": "C", "method": "m", "module": "M"}

    def _render_files(self, hits: List[Dict[str, Any]]):
        self._clear_files()
        self._file_count.configure(text=f"{len(hits)} files")
        for i, h in enumerate(hits):
            fp   = h.get("file_path", "")
            sym  = h.get("symbol_name") or ""
            kind = h.get("kind", "chunk")
            lang = h.get("language", "")
            ls   = h.get("line_start", 0)
            le   = h.get("line_end", 0)
            parts = fp.split("/")
            name  = parts[-1] if parts else fp
            pkg   = "/".join(parts[-3:-1]) if len(parts) > 2 else ""

            bg = "#212123" if i % 2 == 0 else BG
            row = tk.Frame(self._fi, bg=bg, cursor="hand2")
            row.pack(fill=tk.X, padx=0, pady=0)

            icon_f = tk.Frame(row, bg=bg, width=30)
            icon_f.pack(side=tk.LEFT, fill=tk.Y)
            icon_f.pack_propagate(False)
            tk.Label(icon_f, text=self.KIND.get(kind, "·"),
                     fg=ACCENT, bg=bg, font=(MONO, 11, "bold")).pack(
                     expand=True)

            info = tk.Frame(row, bg=bg)
            info.pack(side=tk.LEFT, fill=tk.X, expand=True,
                      padx=(2, 10), pady=6)
            # File name + lang tag on same line
            name_row = tk.Frame(info, bg=bg)
            name_row.pack(fill=tk.X)
            tk.Label(name_row, text=name, fg=FG, bg=bg,
                     font=(MONO, 10, "bold"), anchor="w").pack(side=tk.LEFT)
            if lang:
                tk.Label(name_row, text=f"  {lang}", fg=FG3, bg=bg,
                         font=(SANS, 8)).pack(side=tk.LEFT)
            # Package path
            if pkg:
                tk.Label(info, text=pkg, fg=FG3, bg=bg,
                         font=(SANS, 9), anchor="w").pack(fill=tk.X)
            # Symbol + lines
            detail_parts = []
            if sym:
                detail_parts.append(sym)
            if ls:
                detail_parts.append(f"L{ls}–{le}")
            if detail_parts:
                tk.Label(info, text="  ".join(detail_parts), fg=FG2, bg=bg,
                         font=(MONO, 9), anchor="w").pack(fill=tk.X)

    # ── Response text ───────────────────────────────────────────────────────────

    def _write_response(self, text: str):
        self._resp.configure(state=tk.NORMAL)
        self._resp.delete("1.0", tk.END)
        self._resp.insert(tk.END, text)
        self._resp.configure(state=tk.DISABLED)

    def _synthesize(self, hits: List[Dict[str, Any]]) -> str:
        if not hits:
            return (
                "No indexed artifacts matched.\n\n"
                "Build the corpus first:\n"
                "  python3 evaluation/build_freecad_corpus.py"
            )
        lines = [f"{len(hits)} artifact(s) retrieved and ranked.\n"]
        for i, h in enumerate(hits[:6], 1):
            fp   = h.get("file_path", "")
            sym  = h.get("symbol_name") or ""
            kind = h.get("kind", "chunk")
            text = (h.get("text") or "").strip()
            ls, le = h.get("line_start", 0), h.get("line_end", 0)
            loc  = f" L{ls}–{le}" if ls else ""
            lines.append(f"[{i}] {fp}{loc}")
            if sym:
                lines.append(f"    {sym}  [{kind}]")
            if text:
                snip = "\n    ".join(text.splitlines()[:5])
                lines.append(f"    ···\n    {snip}")
            lines.append("")
        lines.append("Ranked by hybrid semantic + lexical score.")
        return "\n".join(lines)

    # ── Drag ────────────────────────────────────────────────────────────────────

    def _drag_start(self, e):
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    # ── Run ─────────────────────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    auto = sys.argv[1] if len(sys.argv) > 1 else None
    SpotlightDemo(auto_query=auto).run()
