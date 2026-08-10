"""Reusable native Tkinter theme for the SOC training desktop application."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


COLORS = {
    "canvas": "#E8F4F4",
    "surface": "#F7FCFC",
    "surface_soft": "#EAF6F7",
    "sidebar": "#103B53",
    "sidebar_text": "#E9FBFF",
    "sidebar_muted": "#A8CCD8",
    "accent": "#19A974",
    "accent_hover": "#12835A",
    "selection": "#1F7AE0",
    "text": "#102A43",
    "muted": "#56737E",
    "border": "#BBD6D8",
    "success": "#29B675",
    "warning": "#B56918",
}

FONT = "Microsoft YaHei UI"


def configure_theme(root: tk.Tk) -> ttk.Style:
    """Apply the platform's lightweight visual system to a Tk root window."""
    root.configure(background=COLORS["canvas"])
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("App.TFrame", background=COLORS["canvas"])
    style.configure("Surface.TFrame", background=COLORS["surface"])
    style.configure("Card.TFrame", background=COLORS["surface"], relief="flat")
    style.configure("Soft.TFrame", background=COLORS["surface_soft"])
    style.configure("Sidebar.TFrame", background=COLORS["sidebar"])
    style.configure("Title.TLabel", background=COLORS["surface"], foreground=COLORS["text"], font=(FONT, 20, "bold"))
    style.configure("Subtitle.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=(FONT, 10))
    style.configure("CardTitle.TLabel", background=COLORS["surface"], foreground=COLORS["text"], font=(FONT, 11, "bold"))
    style.configure("CardText.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=(FONT, 9))
    style.configure("Metric.TLabel", background=COLORS["surface"], foreground=COLORS["text"], font=(FONT, 18, "bold"))
    style.configure("SidebarTitle.TLabel", background=COLORS["sidebar"], foreground=COLORS["sidebar_text"], font=(FONT, 15, "bold"))
    style.configure("SidebarText.TLabel", background=COLORS["sidebar"], foreground=COLORS["sidebar_muted"], font=(FONT, 9))
    style.configure("TButton", font=(FONT, 10), padding=(12, 8), borderwidth=0)
    style.configure("Accent.TButton", background=COLORS["accent"], foreground="#FFFFFF", padding=(18, 10))
    style.map("Accent.TButton", background=[("active", COLORS["accent_hover"]), ("disabled", "#93D8BD")])
    style.configure("Secondary.TButton", background=COLORS["surface_soft"], foreground=COLORS["text"])
    style.map("Secondary.TButton", background=[("active", "#D7EDF0")])
    style.configure("Sidebar.TButton", background=COLORS["sidebar"], foreground=COLORS["sidebar_muted"], font=(FONT, 12), anchor="w", padding=(16, 12))
    style.map("Sidebar.TButton", background=[("active", "#14516E")], foreground=[("active", "#FFFFFF")])
    style.configure("SidebarActive.TButton", background=COLORS["selection"], foreground="#FFFFFF", font=(FONT, 12), anchor="w", padding=(16, 12))
    style.map("SidebarActive.TButton", background=[("active", "#1766BB")])
    style.configure("Card.TLabelframe", background=COLORS["surface"], bordercolor=COLORS["border"], relief="solid")
    style.configure("Card.TLabelframe.Label", background=COLORS["surface"], foreground=COLORS["text"], font=(FONT, 10, "bold"))
    style.configure("TEntry", fieldbackground="#FFFFFF", foreground=COLORS["text"], padding=7)
    style.configure("TCheckbutton", background=COLORS["surface"], foreground=COLORS["text"], font=(FONT, 9))
    style.configure(
        "Training.Horizontal.TProgressbar",
        background=COLORS["success"],
        lightcolor=COLORS["success"],
        darkcolor=COLORS["success"],
        troughcolor="#E5E7EB",
        bordercolor="#E5E7EB",
        thickness=12,
    )
    style.configure("TNotebook", background=COLORS["surface"], borderwidth=0)
    style.configure("TNotebook.Tab", background=COLORS["surface_soft"], foreground=COLORS["muted"], padding=(14, 8), font=(FONT, 9))
    style.map("TNotebook.Tab", background=[("selected", COLORS["surface"])], foreground=[("selected", COLORS["selection"])])
    style.configure("Treeview", background="#FFFFFF", fieldbackground="#FFFFFF", foreground=COLORS["text"], rowheight=30, font=(FONT, 9), bordercolor=COLORS["border"])
    style.configure("Treeview.Heading", background=COLORS["surface_soft"], foreground=COLORS["text"], font=(FONT, 9, "bold"), relief="flat")
    return style
