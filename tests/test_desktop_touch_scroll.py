from __future__ import annotations

from types import SimpleNamespace
import unittest
import tkinter as tk

from src.desktop.app import DesktopTrainingApp


class FakeWidget:
    def __init__(self, name: str, parent: "FakeWidget | None" = None, widget_class: str = "Frame") -> None:
        self.name = name
        self.parent = parent
        self.widget_class = widget_class

    def winfo_parent(self) -> str:
        return self.parent.name if self.parent is not None else ""

    def nametowidget(self, name: str) -> "FakeWidget":
        current: FakeWidget | None = self
        while current is not None:
            if current.name == name:
                return current
            current = current.parent
        raise KeyError(name)

    def winfo_class(self) -> str:
        return self.widget_class


class FakeCanvas:
    def __init__(self, first: float = 0.25, last: float = 0.75) -> None:
        self.first = first
        self.last = last
        self.calls: list[tuple[int, str]] = []

    def yview(self) -> tuple[float, float]:
        return self.first, self.last

    def yview_scroll(self, number: int, what: str) -> None:
        self.calls.append((number, what))
        span = self.last - self.first
        self.first = min(1.0 - span, max(0.0, self.first + number * 0.1))
        self.last = self.first + span


def _app(*, first: float = 0.25, last: float = 0.75) -> tuple[DesktopTrainingApp, FakeWidget, FakeCanvas]:
    app = DesktopTrainingApp.__new__(DesktopTrainingApp)
    app.content = FakeWidget("content")
    app.content_canvas = FakeCanvas(first, last)
    app._scroll_delta_remainder = 0.0
    app._scroll_binding_tokens = {}
    return app, app.content, app.content_canvas


class TouchScrollTests(unittest.TestCase):
    def test_macos_delta_is_continuous_and_preserves_direction(self) -> None:
        app, content, canvas = _app()
        event = SimpleNamespace(widget=content, delta=0.25, num=None)

        app._on_content_mouse_wheel(event, platform_name="darwin")
        self.assertEqual(canvas.calls, [])
        app._on_content_mouse_wheel(event, platform_name="darwin")
        app._on_content_mouse_wheel(event, platform_name="darwin")
        app._on_content_mouse_wheel(event, platform_name="darwin")

        self.assertEqual(canvas.calls, [(-1, "units")])

    def test_windows_mouse_wheel_and_x11_buttons_keep_existing_direction(self) -> None:
        app, content, canvas = _app()
        app._on_content_mouse_wheel(SimpleNamespace(widget=content, delta=120, num=None), platform_name="win32")
        app._on_content_mouse_wheel(SimpleNamespace(widget=content, delta=0, num=5), platform_name="linux")
        self.assertEqual(canvas.calls, [(-1, "units"), (1, "units")])

    def test_nested_child_routes_to_page_canvas(self) -> None:
        app, content, canvas = _app()
        nested = FakeWidget("nested", content)
        app._on_content_mouse_wheel(SimpleNamespace(widget=nested, delta=-120, num=None), platform_name="win32")
        self.assertEqual(canvas.calls, [(1, "units")])

    def test_text_combo_and_list_keep_scroll_priority(self) -> None:
        app, content, canvas = _app()
        for widget_class in ("Text", "TCombobox", "Listbox"):
            child = FakeWidget(widget_class.lower(), content, widget_class)
            result = app._on_content_mouse_wheel(SimpleNamespace(widget=child, delta=-120, num=None), platform_name="win32")
            self.assertEqual(result, None)
        self.assertEqual(canvas.calls, [])

    def test_no_overflow_or_boundary_does_not_scroll(self) -> None:
        app, content, canvas = _app(first=0.0, last=1.0)
        app._on_content_mouse_wheel(SimpleNamespace(widget=content, delta=-120, num=None), platform_name="win32")
        self.assertEqual(canvas.calls, [])
        app, content, canvas = _app(first=0.0, last=0.5)
        app._on_content_mouse_wheel(SimpleNamespace(widget=content, delta=120, num=None), platform_name="win32")
        self.assertEqual(canvas.calls, [])
        app, content, canvas = _app(first=0.5, last=1.0)
        app._on_content_mouse_wheel(SimpleNamespace(widget=content, delta=-120, num=None), platform_name="win32")
        self.assertEqual(canvas.calls, [])

    def test_bind_is_not_duplicated_and_destroy_unbinds(self) -> None:
        class FakeRoot:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, str]] = []
                self.callbacks: dict[str, set[str]] = {}

            def bind_all(self, sequence: str, callback: object, add: str) -> str:
                self.calls.append(("bind", sequence, add))
                token = f"token-{sequence}-{len(self.callbacks.get(sequence, set()))}"
                self.callbacks.setdefault(sequence, set()).add(token)
                return token

            def bind(self, sequence: str, callback: object, add: str) -> str:
                self.calls.append(("bind", sequence, add))
                return f"root-token-{sequence}"

            def _unbind(self, what: tuple[str, str, str], funcid: str) -> None:
                _, tag, sequence = what
                self.calls.append(("unbind", sequence, funcid))
                self.callbacks.setdefault(sequence, set()).discard(funcid)

        app, _, _ = _app()
        root = FakeRoot()
        unrelated = root.bind_all("<MouseWheel>", object(), add="+")
        app.root = root
        app._bind_content_scrolling()
        app._bind_content_scrolling()
        self.assertEqual([call[0] for call in root.calls[1:4]], ["bind", "bind", "bind"])
        app._unbind_content_scrolling()
        self.assertEqual([call[0] for call in root.calls], ["bind", "bind", "bind", "bind", "bind", "unbind", "unbind", "unbind"])
        self.assertEqual(root.callbacks["<MouseWheel>"], {unrelated})
        self.assertEqual(app._scroll_binding_tokens, {})

    def test_real_tk_unbind_uses_own_funcids_and_destroy_is_safe(self) -> None:
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display is unavailable: {error}")
        root.withdraw()
        try:
            app = DesktopTrainingApp.__new__(DesktopTrainingApp)
            app.root = root
            app._scroll_binding_tokens = {}
            app._scroll_delta_remainder = 0.0
            unrelated = root.bind_all("<MouseWheel>", lambda _event: "break", add="+")
            app._bind_content_scrolling()
            own = app._scroll_binding_tokens["<MouseWheel>"]
            app._unbind_content_scrolling()
            remaining = str(root.tk.call("bind", "all", "<MouseWheel>"))
            self.assertIn(unrelated, remaining)
            self.assertNotIn(own, remaining)
        finally:
            root.destroy()

        root = tk.Tk()
        root.withdraw()
        try:
            app = DesktopTrainingApp.__new__(DesktopTrainingApp)
            app.root = root
            app._scroll_binding_tokens = {}
            app._scroll_delta_remainder = 0.0
            app._bind_content_scrolling()
            root.destroy()
            app._scroll_binding_tokens = {}
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    unittest.main()
