# macOS Finder 风格桌面界面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 SOC 平台重构为蓝绿为主、Finder 式固定侧栏和宽松内容布局的 macOS 风格原生桌面界面。

**Architecture:** `src/desktop/theme.py` 集中定义蓝绿调色板和 ttk 控件风格；`src/desktop/app.py` 保留业务函数，仅替换窗口壳层、导航和内容分组的布局参数。现有右侧滚动容器保持不变。

**Tech Stack:** Python 3.12、Tkinter/ttk、unittest。

## Global Constraints

- 不修改训练参数、训练命令、数据路径、结果目录、模型代码或删除保护。
- 侧栏使用深青蓝，主操作使用青绿色，选中态使用湖蓝。
- 白灰只作为局部输入框、表格和图表底色。
- 右侧内容区必须继续支持滚轮和滚动条，小窗口可访问训练按钮、进度和日志。

---

### Task 1: 蓝绿 macOS 调色板和控件风格

**Files:**
- Modify: `src/desktop/theme.py`
- Modify: `tests/test_desktop_theme.py`

**Interfaces:**
- Produces: `COLORS` including `sidebar`, `accent`, `selection`, `canvas`, and `configure_theme(root)`.

- [ ] **Step 1: Write the failing test**

```python
def test_theme_uses_blue_green_system_palette():
    from src.desktop.theme import COLORS
    self.assertEqual(COLORS["sidebar"], "#103B53")
    self.assertEqual(COLORS["accent"], "#19A974")
    self.assertEqual(COLORS["selection"], "#1F7AE0")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `..\..\work\soc_venv\Scripts\python.exe -m unittest tests\test_desktop_theme.py -v`

Expected: FAIL because the existing purple and orange values differ.

- [ ] **Step 3: Write minimal implementation**

Update `COLORS` and ttk style maps: soft blue-green canvas, deep teal sidebar, blue selection, green accent, rounded-feeling padding, and neutral local surfaces.

- [ ] **Step 4: Run the test to verify it passes**

Run: `..\..\work\soc_venv\Scripts\python.exe -m unittest tests\test_desktop_theme.py -v`

Expected: PASS.

### Task 2: Finder 式窗口壳层与宽松内容间距

**Files:**
- Modify: `src/desktop/app.py`
- Modify: `tests/test_desktop_app.py`

**Interfaces:**
- Consumes: `COLORS`, `configure_theme(root)`.
- Produces: fixed navigation, unchanged `content_canvas`, and title/content gutters.

- [ ] **Step 1: Write the failing test**

```python
def test_desktop_shell_keeps_a_fixed_sidebar_and_roomy_content():
    source = (PROJECT / "src" / "desktop" / "app.py").read_text(encoding="utf-8")
    self.assertIn("width=236", source)
    self.assertIn("padx=36, pady=30", source)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `..\..\work\soc_venv\Scripts\python.exe -m unittest tests\test_desktop_app.py -v`

Expected: FAIL because the existing shell is narrower and has smaller content gutters.

- [ ] **Step 3: Write minimal implementation**

Use a 236px deep-teal sidebar; expand top-level canvas/shell spacing; retain `content_canvas` and all scrolling methods; use a 36px horizontal and 30px vertical inner gutter; increase navigation/button spacing without changing button callbacks.

- [ ] **Step 4: Run the test to verify it passes**

Run: `..\..\work\soc_venv\Scripts\python.exe -m unittest tests\test_desktop_app.py -v`

Expected: PASS.

### Task 3: Verification

**Files:**
- Test: `tests/test_desktop_theme.py`
- Test: `tests/test_desktop_app.py`

- [ ] **Step 1: Run syntax verification**

Run: `..\..\work\soc_venv\Scripts\python.exe -m py_compile src\desktop\theme.py src\desktop\app.py`

Expected: exit code 0.

- [ ] **Step 2: Run complete regression suite**

Run: `..\..\work\soc_venv\Scripts\python.exe -m unittest discover -s tests -v`

Expected: exit code 0 with no failed tests.

- [ ] **Step 3: Commit**

Git is unavailable on this computer; record changed files and verification evidence in the handoff.
