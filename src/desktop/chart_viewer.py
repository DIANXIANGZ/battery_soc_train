"""Interactive, read-only PNG chart viewing for the native desktop UI."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk


MIN_SCALE = 0.8
MAX_SCALE = 3.0
SCALE_STEP = 0.1


def clamp_scale(value: float) -> float:
    """Keep the chart scale within the confirmed 80%–300% range."""
    return round(min(MAX_SCALE, max(MIN_SCALE, value)), 2)


def next_scale(current: float, direction: int) -> float:
    """Return the next 10% zoom step for a positive or negative wheel direction."""
    return clamp_scale(current + SCALE_STEP * (1 if direction > 0 else -1))


class InteractiveChartViewer(tk.Frame):
    """A scrollable PNG chart that supports wheel zoom and click-to-enlarge."""

    def __init__(self, parent: tk.Misc, chart_path: Path, *, allow_expand: bool = True) -> None:
        super().__init__(parent, bg="#FFFFFF")
        self.chart_path = Path(chart_path)
        with Image.open(self.chart_path) as source:
            self.source_image = source.convert("RGBA").copy()
        self.scale = 1.0
        self.allow_expand = allow_expand
        hint = "滚轮缩放 · 单击查看大图" if allow_expand else "滚轮缩放 · 使用下方按钮重置"
        tk.Label(self, text=hint, bg="#FFFFFF", fg="#777487", font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, pady=(0, 6))
        canvas_frame = tk.Frame(self, bg="#FFFFFF")
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg="#FFFFFF", highlightthickness=0, cursor="plus")
        self.horizontal = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.vertical = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.horizontal.set, yscrollcommand=self.vertical.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vertical.grid(row=0, column=1, sticky="ns")
        self.horizontal.grid(row=1, column=0, sticky="ew")
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda _: self._zoom(1))
        self.canvas.bind("<Button-5>", lambda _: self._zoom(-1))
        if allow_expand:
            self.canvas.bind("<Button-1>", self._open_large_window)
        self._render()

    def _render(self) -> None:
        width = max(1, round(self.source_image.width * self.scale))
        height = max(1, round(self.source_image.height * self.scale))
        resized = self.source_image.resize((width, height), Image.Resampling.LANCZOS)
        self.photo_image = ImageTk.PhotoImage(resized)
        self.canvas.delete("chart")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo_image, tags="chart")
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def _on_wheel(self, event: tk.Event) -> str:
        if event.delta:
            self._zoom(1 if event.delta > 0 else -1)
        return "break"

    def _zoom(self, direction: int) -> None:
        scale = next_scale(self.scale, direction)
        if scale != self.scale:
            self.scale = scale
            self._render()

    def reset_zoom(self) -> None:
        self.scale = 1.0
        self._render()

    def _open_large_window(self, _: tk.Event | None = None) -> None:
        window = tk.Toplevel(self)
        window.title(f"大图查看 · {self.chart_path.name}")
        window.geometry("1180x760")
        window.minsize(760, 540)
        outer = tk.Frame(window, bg="#FFFFFF", padx=16, pady=14)
        outer.pack(fill=tk.BOTH, expand=True)
        controls = tk.Frame(outer, bg="#FFFFFF")
        controls.pack(fill=tk.X, pady=(0, 8))
        tk.Label(controls, text="大图查看", bg="#FFFFFF", fg="#26243A", font=("Microsoft YaHei UI", 14, "bold")).pack(side=tk.LEFT)
        viewer = InteractiveChartViewer(outer, self.chart_path, allow_expand=False)
        ttk.Button(controls, text="重置缩放", command=viewer.reset_zoom).pack(side=tk.RIGHT)
        ttk.Button(controls, text="关闭", command=window.destroy).pack(side=tk.RIGHT, padx=(0, 8))
        viewer.pack(fill=tk.BOTH, expand=True)
        window.transient(self.winfo_toplevel())
