"""Polished native Tkinter interface for the local SOC training platform."""

from __future__ import annotations

import json
import os
import random
import sys
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from src.custom_training.algorithms import algorithm_keys, recommend_algorithm
from src.custom_training.admission import assess_custom_training
from src.custom_training.dataset import ALGORITHMS, CustomDatasetConfig, list_sheet_names, read_headers

from src.desktop.charts import ensure_run_charts
from src.desktop.chart_viewer import InteractiveChartViewer
from src.desktop.multistate_charts import build_multistate_charts
from src.desktop.hybrid_charts import build_hybrid_charts
from src.desktop.formal_baselines import build_formal_baseline_command, load_formal_baselines
from src.desktop.theme import COLORS, configure_theme
from src.desktop.training_controller import TrainingController, epoch_progress, smooth_progress_step
from src.evaluation.nasa_lifecycle_experiments import result_dir_name
from src.platform.platform_core import (
    PlatformStore,
    build_hybrid_command,
    build_custom_command,
    build_lifecycle_command,
    build_multistate_command,
    build_soc_command,
    latest_complete_run_result,
    read_generalization_summary,
    read_hybrid_result,
    read_nasa_lifecycle_result,
    read_run_result,
    resolve_training_python,
    summarize_csv,
)
from src.project_paths import DataCenterPaths


def deletion_math_challenge() -> tuple[str, int]:
    """Create a non-negative addition or subtraction challenge within 100."""
    generator = random.SystemRandom()
    if generator.choice((True, False)):
        left = generator.randint(0, 100)
        right = generator.randint(0, 100 - left)
        return f"{left} + {right}", left + right
    left = generator.randint(0, 100)
    right = generator.randint(0, left)
    return f"{left} - {right}", left - right


class DesktopTrainingApp:
    def __init__(self, root: tk.Tk | None, project_root: Path) -> None:
        self.root = root
        self.project_root = Path(project_root).resolve()
        self.config_path = self.project_root / "configs" / "paths.json"
        self.paths: DataCenterPaths | None = None
        self.store: PlatformStore | None = None
        self.project = None
        self.projects: dict[str, object] = {}
        self.controller = TrainingController()
        self.current_run: Path | None = None
        self.training_epochs = 1
        self.training_progress_target = 0.0
        self.training_progress_display = 0.0
        self.training_log_buffer = ""
        self._progress_animation_running = False
        self.progress_value: tk.DoubleVar | None = None
        self.progress_text: tk.StringVar | None = None
        self.progress_frame: tk.Frame | None = None
        self.training_form_card: tk.Frame | None = None
        self.start_button: ttk.Button | None = None
        self.custom_algorithm_var: tk.StringVar | None = None
        self.custom_admission_text: tk.StringVar | None = None
        self.custom_recommendation_text: tk.StringVar | None = None
        self.log_text: tk.Text | None = None
        self.content_canvas: tk.Canvas | None = None
        self._content_window: int | None = None
        self._images: list[tk.PhotoImage] = []
        self._nav_buttons: dict[str, ttk.Button] = {}
        self._message = "正在读取数据中心配置。"
        self._load_configuration()
        if self.root is not None:
            self._build_window()

    @classmethod
    def create_for_test(cls, project_root: Path) -> "DesktopTrainingApp":
        return cls(None, project_root)

    @staticmethod
    def default_settings() -> dict[str, object]:
        return {
            "window": 60,
            "epochs": 40,
            "max_train": 40000,
            "max_valid": 20000,
            "max_test": 20000,
            "hidden": 32,
            "learning_rate": 0.0003,
            "patience": 9,
            "dropout": 0.1,
            "weight_decay": 1e-4,
            "lr_patience": 3,
            "lr_factor": 0.5,
            "min_learning_rate": 3e-5,
            "min_delta": 1e-5,
            "gradient_clip": 1.0,
            "seed": 42,
            "add_delta_ah": True,
            "balance_soc": True,
        }

    @staticmethod
    def default_settings_for(project_name: str) -> dict[str, object]:
        """Use conservative NASA defaults without changing existing A123 defaults."""

        if project_name == "NASA 五状态（改进）":
            return {"stage": "formal", "seed": 42}
        settings = DesktopTrainingApp.default_settings()
        if project_name == "NASA 五状态":
            settings.update({"window": 30, "batch_size": 128, "max_train": 0, "max_valid": 0, "max_test": 0})
        return settings


    def _load_configuration(self) -> None:
        try:
            paths = DataCenterPaths.from_config(self.config_path)
        except ValueError:
            self._message = "尚未配置数据中心。请点击“选择数据中心”。"
            return
        if not paths.root.is_dir():
            self._message = "配置的数据中心不存在。请重新选择数据中心。"
            return
        self.paths = paths
        self.store = PlatformStore(paths.platform_store_dir)
        soc_project = self.store.ensure_soc_project(
            self.project_root / "src" / "training" / "train_lstm.py",
            paths.training_csv,
        )
        hybrid_project = self.store.ensure_nasa_hybrid_project(
            self.project_root / "src" / "training" / "train_nasa_hybrid.py",
            paths.nasa_improved_training_dir / "nasa_lifecycle_cycles.csv",
        )
        self.projects = {
            soc_project.name: soc_project,
            hybrid_project.name: hybrid_project,
        }
        self.projects.update({project.name: project for project in self.store.list_projects() if project.name not in {"NASA 五状态", "NASA 生命周期模型"} and project.name != "NASA 五状态"})
        self.project = soc_project
        self._message = "数据中心已就绪。" if self.training_ready() else "数据中心已就绪；请先运行“初始化环境.bat”。"

    def training_ready(self) -> bool:
        if self.paths is None:
            return False
        try:
            python = resolve_training_python(self.project_root)
        except FileNotFoundError:
            return False
        return python.is_file() and self.project is not None and Path(self.project.data_path).is_file()

    def startup_message(self) -> str:
        return self._message

    def _build_window(self) -> None:
        assert self.root is not None
        configure_theme(self.root)
        self.root.title("SOC 电池训练平台")
        self.root.minsize(1000, 650)
        self.root.geometry("1180x760")

        canvas = tk.Frame(self.root, bg=COLORS["canvas"])
        canvas.pack(fill=tk.BOTH, expand=True, padx=26, pady=22)
        shell = tk.Frame(canvas, bg=COLORS["surface"], highlightthickness=1, highlightbackground=COLORS["border"])
        shell.pack(fill=tk.BOTH, expand=True)

        navigation = tk.Frame(shell, bg=COLORS["sidebar"], width=236)
        navigation.pack(side=tk.LEFT, fill=tk.Y)
        navigation.pack_propagate(False)
        main = tk.Frame(shell, bg=COLORS["surface"])
        main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content_scrollbar = ttk.Scrollbar(main, orient=tk.VERTICAL)
        content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=1)
        self.content_canvas = tk.Canvas(main, bg=COLORS["surface"], highlightthickness=0, yscrollcommand=content_scrollbar.set)
        self.content_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content_scrollbar.configure(command=self.content_canvas.yview)
        self.content = tk.Frame(self.content_canvas, bg=COLORS["surface"], padx=36, pady=30)
        self._content_window = self.content_canvas.create_window((0, 0), window=self.content, anchor=tk.NW)
        self.content.bind("<Configure>", self._update_content_scroll_region)
        self.content_canvas.bind("<Configure>", self._resize_content_width)
        main.bind_all("<MouseWheel>", self._on_content_mouse_wheel, add="+")

        tk.Label(navigation, text="SOC", bg=COLORS["sidebar"], fg=COLORS["sidebar_text"], font=("Microsoft YaHei UI", 20, "bold")).pack(anchor=tk.W, padx=24, pady=(32, 0))
        tk.Label(navigation, text="TRAINING LAB", bg=COLORS["sidebar"], fg=COLORS["sidebar_muted"], font=("Microsoft YaHei UI", 9, "bold")).pack(anchor=tk.W, padx=24, pady=(2, 32))
        self.project_var = tk.StringVar(value=self.project.name if self.project is not None else "")
        selector = ttk.Combobox(navigation, textvariable=self.project_var, values=[*self.projects, "自定义数据集…"], state="readonly", width=17)
        self.project_selector = selector
        selector.pack(fill=tk.X, padx=16, pady=(0, 18))
        selector.bind("<<ComboboxSelected>>", self._select_project)
        ttk.Button(navigation, text="导入自定义数据", style="Secondary.TButton", command=self.open_custom_dataset_dialog).pack(fill=tk.X, padx=16, pady=(0, 12))
        for key, label, callback in (
            ("overview", "⌂  项目概览", self.show_overview),
            ("formal_baselines", "▤  四目标正式基线", self.show_formal_baselines),
            ("dataset", "▣  数据集", self.show_dataset),
            ("training", "◫  训练方案", self.show_training),
            ("results", "▤  实验结果", self.show_results),
        ):
            button = ttk.Button(navigation, text=label, style="Sidebar.TButton", command=callback)
            button.pack(fill=tk.X, padx=16, pady=5)
            self._nav_buttons[key] = button
        ttk.Separator(navigation).pack(fill=tk.X, padx=24, pady=22)
        ttk.Button(navigation, text="选择数据中心", style="Secondary.TButton", command=self.choose_data_center).pack(fill=tk.X, padx=16)
        self.status_label = tk.Label(navigation, text=self._message, bg=COLORS["sidebar"], fg=COLORS["sidebar_muted"], font=("Microsoft YaHei UI", 9), justify=tk.LEFT, wraplength=150)
        self.status_label.pack(side=tk.BOTTOM, anchor=tk.W, padx=24, pady=28)
        self.show_overview()

    def _set_active_page(self, page: str) -> None:
        for key, button in self._nav_buttons.items():
            button.configure(style="SidebarActive.TButton" if key == page else "Sidebar.TButton")

    def _select_project(self, _: object = None) -> None:
        selected = self.project_var.get()
        if selected == "自定义数据集…":
            self.open_custom_dataset_dialog()
            return
        if selected not in self.projects:
            return
        self.project = self.projects[selected]
        self.show_overview()

    @staticmethod
    def _recommended_algorithm(targets: tuple[str, ...]) -> str:
        return recommend_algorithm(targets)

    def _custom_project_state(self) -> tuple[dict, dict]:
        if self.store is None or self.project is None:
            raise ValueError("当前没有自定义数据集项目。")
        config = self.store.custom_config_for(self.project)
        try:
            admission = self.store.custom_admission_for(self.project)
        except ValueError:
            admission = {
                "configuration_allowed": True,
                "training_allowed": False,
                "blockers": ["admission_missing_or_invalid"],
            }
        if not isinstance(admission.get("target_report"), dict):
            report_config = CustomDatasetConfig(
                source_path=Path(self.project.data_path),
                sheet_name=None,
                time_column=config.get("time_column"),
                feature_columns=tuple(str(item) for item in config.get("feature_columns", ())),
                target_columns=tuple(str(item) for item in config.get("target_columns", ())),
                algorithm=str(config.get("algorithm", "")),
                role_columns=tuple(tuple(str(value) for value in item) for item in config.get("role_columns", ())),
            )
            report = asdict(assess_custom_training(report_config, manifest=None))
            admission = {
                **admission,
                "target_report": json.loads(json.dumps(report, ensure_ascii=False)),
            }
        return config, admission

    @staticmethod
    def _custom_admission_summary(admission: dict) -> str:
        status = "已授权" if admission.get("training_allowed") is True else "阻塞"
        blockers = admission.get("blockers", [])
        lines = [f"数据准入门禁：{status}"]
        if blockers:
            lines.append("全局阻塞：" + "、".join(str(item) for item in blockers))
        report = admission.get("target_report")
        if isinstance(report, dict):
            lines.append(f"泛化等级：{report.get('generalization_level', 'configuration_only')}")
            targets = report.get("targets")
            if isinstance(targets, list):
                for item in targets:
                    if not isinstance(item, dict):
                        continue
                    target_blockers = item.get("blockers")
                    detail = "、".join(str(value) for value in target_blockers) if target_blockers else "已通过"
                    lines.append(f"{item.get('target', 'unknown')}：{detail}")
        elif not blockers:
            lines.append("全局阻塞：未提供授权证据")
        return "\n".join(lines)

    def _save_custom_algorithm(self) -> None:
        if self.store is None or self.project is None or self.custom_algorithm_var is None:
            return
        try:
            record = self.store.update_custom_algorithm(self.project, self.custom_algorithm_var.get())
        except ValueError as error:
            messagebox.showerror("无法保存算法配置", str(error))
            return
        admission = record["custom_admission"]
        if self.custom_admission_text is not None:
            self.custom_admission_text.set(self._custom_admission_summary(admission))
        self._set_start_enabled(False)

    def open_custom_dataset_dialog(self) -> None:
        source_name = filedialog.askopenfilename(filetypes=[("数据文件", "*.csv *.xlsx *.xls")])
        if not source_name or self.root is None or self.store is None:
            self.project_var.set(self.project.name if self.project is not None else "")
            return
        source = Path(source_name)
        try:
            sheets = list_sheet_names(source); headers = read_headers(source, sheets[0] if sheets else None)
        except ValueError as error:
            messagebox.showerror("无法导入数据", str(error)); return
        dialog = tk.Toplevel(self.root); dialog.title("导入自定义数据集"); dialog.transient(self.root); dialog.grab_set(); dialog.configure(bg=COLORS["surface"])
        name = tk.StringVar(value=f"自定义 {source.stem}"); sheet = tk.StringVar(value=sheets[0] if sheets else "")
        algorithm = tk.StringVar(value="lstm"); time = tk.StringVar(value="")
        for label, variable in (("项目名称", name), ("工作表", sheet), ("时间列（可选）", time)):
            ttk.Label(dialog, text=label).pack(anchor=tk.W, padx=18, pady=(12,2)); ttk.Combobox(dialog, textvariable=variable, values=(headers if label.startswith("时间") else sheets), width=38).pack(padx=18)
        ttk.Label(dialog, text="特征列（多选）").pack(anchor=tk.W, padx=18, pady=(12,2)); features=tk.Listbox(dialog, selectmode=tk.MULTIPLE, height=6); targets=tk.Listbox(dialog, selectmode=tk.MULTIPLE, height=6)
        for header in headers: features.insert(tk.END,header); targets.insert(tk.END,header)
        features.pack(fill=tk.X,padx=18); ttk.Label(dialog,text="预测目标列（多选）").pack(anchor=tk.W,padx=18,pady=(10,2)); targets.pack(fill=tk.X,padx=18)
        ttk.Label(dialog,text="训练算法（LSTM / GRU / XGBoost / Transformer）").pack(anchor=tk.W,padx=18,pady=(10,2)); ttk.Combobox(dialog,textvariable=algorithm,values=ALGORITHMS,state="readonly",width=38).pack(padx=18)
        def create() -> None:
            chosen_features=tuple(features.get(i) for i in features.curselection()); chosen_targets=tuple(targets.get(i) for i in targets.curselection())
            if not chosen_features or not chosen_targets: messagebox.showerror("无法导入", "请至少选择一个特征列和一个预测目标列。", parent=dialog); return
            config=CustomDatasetConfig(source, sheet.get() or None, time.get() or None, chosen_features, chosen_targets, algorithm.get())
            try: project=self.store.create_custom_project(name.get(),config,self.project_root/"src"/"training"/"train_custom.py")
            except ValueError as error: messagebox.showerror("无法导入",str(error),parent=dialog); return
            self.projects[project.name]=project; self.project=project; self.project_var.set(project.name); self.project_selector.configure(values=[*self.projects,"自定义数据集…"]); dialog.destroy(); self.show_dataset()
        ttk.Button(dialog,text="导入并创建项目",style="Accent.TButton",command=create).pack(anchor=tk.E,padx=18,pady=18)

    def _clear_content(self) -> None:
        self._images = []
        for child in self.content.winfo_children():
            child.destroy()
        if self.content_canvas is not None:
            self.content_canvas.yview_moveto(0)

    def _update_content_scroll_region(self, _: object = None) -> None:
        if self.content_canvas is not None:
            self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    def _resize_content_width(self, event: tk.Event) -> None:
        if self.content_canvas is not None and self._content_window is not None:
            self.content_canvas.itemconfigure(self._content_window, width=event.width)

    def _is_content_widget(self, widget: tk.Misc | None) -> bool:
        while widget is not None:
            if widget is self.content:
                return True
            parent_name = widget.winfo_parent()
            if not parent_name:
                return False
            try:
                widget = widget.nametowidget(parent_name)
            except (KeyError, tk.TclError):
                return False
        return False

    def _on_content_mouse_wheel(self, event: tk.Event) -> None:
        if self.content_canvas is None or not self._is_content_widget(event.widget):
            return
        steps = -1 if event.delta > 0 else 1
        self.content_canvas.yview_scroll(steps, "units")

    @staticmethod
    def _widget_exists(widget: tk.Misc | None) -> bool:
        if widget is None:
            return False
        try:
            return bool(widget.winfo_exists())
        except tk.TclError:
            return False

    def _set_progress_visible(self, visible: bool) -> None:
        if not self._widget_exists(self.progress_frame):
            return
        assert self.progress_frame is not None
        if visible:
            pack_options: dict[str, object] = {"fill": tk.X, "pady": (0, 10)}
            if self._widget_exists(self.training_form_card):
                pack_options["before"] = self.training_form_card
            self.progress_frame.pack(**pack_options)
        else:
            self.progress_frame.pack_forget()

    def _set_start_enabled(self, enabled: bool) -> None:
        if self._widget_exists(self.start_button):
            assert self.start_button is not None
            self.start_button.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def _set_progress_target(self, progress: float) -> None:
        self.training_progress_target = min(100.0, max(0.0, float(progress)))
        if self.progress_text is not None:
            self.progress_text.set(f"正在训练：{int(self.training_progress_target)}%")
        if not self._progress_animation_running:
            self._progress_animation_running = True
            self._animate_progress()

    def _animate_progress(self) -> None:
        self.training_progress_display = smooth_progress_step(
            self.training_progress_display,
            self.training_progress_target,
        )
        if self.progress_value is not None:
            self.progress_value.set(self.training_progress_display)
        if self.training_progress_display == self.training_progress_target:
            self._progress_animation_running = False
            return
        assert self.root is not None
        self.root.after(20, self._animate_progress)

    def _title(self, title: str, subtitle: str) -> None:
        tk.Label(self.content, text=title, bg=COLORS["surface"], fg=COLORS["text"], font=("Microsoft YaHei UI", 20, "bold")).pack(anchor=tk.W)
        tk.Label(self.content, text=subtitle, bg=COLORS["surface"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 10)).pack(anchor=tk.W, pady=(4, 18))

    def _card(self, parent: tk.Misc, padding: int = 16, background: str | None = None) -> tk.Frame:
        color = background or COLORS["surface"]
        return tk.Frame(parent, bg=color, padx=padding, pady=padding, highlightthickness=1, highlightbackground=COLORS["border"])

    def _require_paths(self) -> bool:
        if self.paths is not None and self.project is not None:
            return True
        if self.root is not None:
            messagebox.showwarning("需要数据中心", self._message)
        return False

    def choose_data_center(self) -> None:
        if self.root is None:
            return
        selected = filedialog.askdirectory(title="选择 SOC 电池数据中心")
        if not selected:
            return
        root = Path(selected)
        if not (root / "02_训练数据").is_dir():
            messagebox.showerror("目录不正确", "请选择包含“02_训练数据”文件夹的数据中心根目录。")
            return
        DataCenterPaths.save_config(self.config_path, root)
        self.paths = self.store = self.project = None
        self._load_configuration()
        self.status_label.configure(text=self._message)
        self.show_overview()

    def _latest_result(self):
        assert self.project is not None
        return latest_complete_run_result(self.project.path / "runs")

    def _metric_card(self, parent: tk.Misc, label: str, value: str, note: str, accent: bool = False) -> None:
        color = COLORS["sidebar"] if accent else COLORS["surface"]
        frame = self._card(parent, 14, color)
        frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        foreground = COLORS["sidebar_text"] if accent else COLORS["text"]
        muted = COLORS["sidebar_muted"] if accent else COLORS["muted"]
        tk.Label(frame, text=label, bg=color, fg=muted, font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W)
        tk.Label(frame, text=value, bg=color, fg=foreground, font=("Microsoft YaHei UI", 18, "bold")).pack(anchor=tk.W, pady=(4, 2))
        tk.Label(frame, text=note, bg=color, fg=muted, font=("Microsoft YaHei UI", 8)).pack(anchor=tk.W)

    def _show_chart(self, parent: tk.Misc, chart_path: Path | None) -> None:
        if chart_path is None:
            tk.Label(parent, text="尚无可用图表。", bg=COLORS["surface"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 10)).pack(anchor=tk.W, pady=10)
            return
        if chart_path.suffix.lower() != ".png":
            tk.Label(parent, text="当前结果仅有 SVG 图表；请在结果目录中打开。", bg=COLORS["surface"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 10)).pack(anchor=tk.W, pady=10)
            return
        try:
            viewer = InteractiveChartViewer(parent, chart_path)
        except (OSError, tk.TclError):
            tk.Label(parent, text=f"无法显示图像：{chart_path.name}", bg=COLORS["surface"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 10)).pack(anchor=tk.W, pady=10)
            return
        # 图表支持滚轮缩放，并可单击打开独立大图窗口。
        viewer.pack(fill=tk.BOTH, expand=True)

    def show_overview(self) -> None:
        self._set_active_page("overview")
        self._clear_content()
        banner = tk.Frame(self.content, bg=COLORS["accent"], padx=22, pady=17)
        banner.pack(fill=tk.X, pady=(0, 16))
        tk.Label(banner, text="SOC 电池训练平台", bg=COLORS["accent"], fg="#FFFFFF", font=("Microsoft YaHei UI", 17, "bold")).pack(anchor=tk.W)
        tk.Label(banner, text="每一次训练均保存为独立实验，不会覆盖已有模型、图表或记录。", bg=COLORS["accent"], fg="#FFF5D6", font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, pady=(5, 0))
        if not self._require_paths():
            return
        result = self._latest_result()
        if result is None:
            empty = self._card(self.content, 18, COLORS["surface_soft"])
            empty.pack(fill=tk.X)
            tk.Label(empty, text="暂无实验结果", bg=COLORS["surface_soft"], fg=COLORS["text"], font=("Microsoft YaHei UI", 13, "bold")).pack(anchor=tk.W)
            tk.Label(empty, text="当前没有包含完整指标和预测数据的训练实验，请前往“训练方案”开始新的训练。", bg=COLORS["surface_soft"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, pady=(6, 0))
            return
        if self.project is not None and self.project.name == "NASA 五状态":
            target_metrics = json.loads((result.path / "metrics_by_target.json").read_text(encoding="utf-8"))
            metrics_row = tk.Frame(self.content, bg=COLORS["surface"])
            metrics_row.pack(fill=tk.X, pady=(0, 16))
            self._metric_card(metrics_row, "SOC · MAE", f"{float(target_metrics['soc']['MAE']) * 100:.2f}%", "越低越好")
            self._metric_card(metrics_row, "SOE · MAE", f"{float(target_metrics['soe']['MAE']) * 100:.2f}%", "越低越好")
            self._metric_card(metrics_row, "RUL · MAE", f"{float(target_metrics['rul_cycles']['MAE']):.2f}", "cycles", accent=True)
            chart_card = self._card(self.content, 14)
            chart_card.pack(fill=tk.BOTH, expand=True)
            tk.Label(chart_card, text="NASA 五状态：SOC 预测趋势", bg=COLORS["surface"], fg=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 8))
            self._show_chart(chart_card, build_multistate_charts(result.path).get("soc"))
            return
        metrics_row = tk.Frame(self.content, bg=COLORS["surface"])
        metrics_row.pack(fill=tk.X, pady=(0, 16))
        assert result.metrics is not None
        self._metric_card(metrics_row, "平均绝对误差 · MAE", f"{float(result.metrics['MAE_pct']):.2f}%", "越低越好")
        self._metric_card(metrics_row, "均方根误差 · RMSE", f"{float(result.metrics['RMSE_pct']):.2f}%", "综合误差")
        self._metric_card(metrics_row, "独立测试样本", f"{int(result.metrics['n_test']):,}", "最近一次训练", accent=True)
        chart_card = self._card(self.content, 14)
        chart_card.pack(fill=tk.BOTH, expand=True)
        header = tk.Frame(chart_card, bg=COLORS["surface"])
        header.pack(fill=tk.X, pady=(0, 8))
        tk.Label(header, text="最近一次 SOC 预测趋势", bg=COLORS["surface"], fg=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold")).pack(side=tk.LEFT)
        ttk.Button(header, text="查看实验结果", style="Secondary.TButton", command=self.show_results).pack(side=tk.RIGHT)
        self._show_chart(chart_card, result.chart_path)

    def show_formal_baselines(self) -> None:
        """Show the archived four-target baselines without opening sample data."""
        self._set_active_page("formal_baselines")
        self._clear_content()
        self._title("四目标正式基线", "只读查看已完成基线；打开或刷新不会重新运行训练。")
        summary = load_formal_baselines(self.project_root)
        if summary.status == "UNAVAILABLE":
            card = self._card(self.content, 16, "#FFF7E6")
            card.pack(fill=tk.X)
            tk.Label(card, text="正式基线不可用", bg="#FFF7E6", fg=COLORS["warning"], font=("Microsoft YaHei UI", 12, "bold")).pack(anchor=tk.W)
            tk.Label(card, text=summary.reason, bg="#FFF7E6", fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, pady=(5, 0))
            return
        for target in ("soc", "system_soe", "soh", "sot"):
            baseline = summary.targets[target]
            card = self._card(self.content, 14, COLORS["surface_soft"])
            card.pack(fill=tk.X, pady=(0, 12))
            header = tk.Frame(card, bg=COLORS["surface_soft"])
            header.pack(fill=tk.X)
            tk.Label(header, text=baseline.display_name, bg=COLORS["surface_soft"], fg=COLORS["text"], font=("Microsoft YaHei UI", 12, "bold")).pack(side=tk.LEFT)
            tk.Label(header, text=baseline.status, bg=COLORS["surface_soft"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(side=tk.RIGHT)
            tk.Label(card, text=f"模型：{baseline.model}", bg=COLORS["surface_soft"], fg=COLORS["text"], font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, pady=(7, 0))
            tk.Label(card, text=f"适用范围：{baseline.scope}", bg=COLORS["surface_soft"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9), wraplength=860, justify=tk.LEFT).pack(anchor=tk.W, pady=(4, 0))
            metric_text = "；".join(f"{key}={value}" for key, value in baseline.metrics.items()) or "未提供指标"
            tk.Label(card, text=f"核心指标：{metric_text}", bg=COLORS["surface_soft"], fg=COLORS["text"], font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, pady=(4, 0))
            tk.Label(card, text=f"数据版本：{baseline.dataset_path or '不可用'}", bg=COLORS["surface_soft"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 8), wraplength=860, justify=tk.LEFT).pack(anchor=tk.W, pady=(4, 0))
            tk.Label(card, text=f"结果目录：{baseline.result_path or '不可用'}", bg=COLORS["surface_soft"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 8), wraplength=860, justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 0))
            tk.Label(card, text=f"正式报告：{baseline.report_path or '未在归档摘要中提供'}", bg=COLORS["surface_soft"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 8), wraplength=860, justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 0))
            if baseline.reason:
                tk.Label(card, text=f"状态说明：{baseline.reason}", bg=COLORS["surface_soft"], fg=COLORS["warning"], font=("Microsoft YaHei UI", 9), wraplength=860, justify=tk.LEFT).pack(anchor=tk.W, pady=(4, 0))
            actions = tk.Frame(card, bg=COLORS["surface_soft"])
            actions.pack(anchor=tk.W, pady=(8, 0))
            if baseline.report_path is not None:
                ttk.Button(actions, text="打开报告", style="Secondary.TButton", command=lambda path=baseline.report_path: self._open_formal_path(path)).pack(side=tk.LEFT, padx=(0, 8))
            if baseline.result_path is not None:
                ttk.Button(actions, text="打开结果目录", style="Secondary.TButton", command=lambda path=baseline.result_path: self._open_formal_path(path)).pack(side=tk.LEFT, padx=(0, 8))
            spec = build_formal_baseline_command(baseline, self.project_root)
            if spec.available:
                ttk.Button(actions, text="受控启动正式基线", style="Accent.TButton", command=lambda name=target: self._start_formal_baseline(name)).pack(side=tk.LEFT)
            else:
                tk.Label(actions, text=f"不可启动：{spec.reason}", bg=COLORS["surface_soft"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT)

    @staticmethod
    def _open_formal_path(path: Path) -> None:
        if path.is_file() or path.is_dir():
            os.startfile(str(path))

    def _start_formal_baseline(self, target: str) -> None:
        summary = load_formal_baselines(self.project_root)
        baseline = summary.targets.get(target)
        if baseline is None:
            messagebox.showerror("无法启动", "正式基线条目不存在。")
            return
        spec = build_formal_baseline_command(baseline, self.project_root)
        if not spec.available or spec.output_path is None:
            messagebox.showwarning("无法启动", spec.reason)
            return
        if not messagebox.askyesno("确认启动", f"将使用已验证的固定入口启动 {baseline.display_name}，结果写入新目录：\n{spec.output_path}\n\n是否继续？"):
            return
        try:
            self.controller.start(list(spec.command), spec.output_path, self.project_root)
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            messagebox.showerror("启动失败", str(error))
            return
        messagebox.showinfo("已启动", f"已启动 {baseline.display_name} 受控运行。\n结果目录：{spec.output_path}")

    def show_dataset(self) -> None:
        self._set_active_page("dataset")
        self._clear_content()
        self._title("数据集", "训练数据保持只读；平台仅用于查看摘要和启动训练。")
        if not self._require_paths():
            return
        assert self.project is not None
        data_path = Path(self.project.data_path)
        if not data_path.is_file():
            tk.Label(self.content, text=f"训练数据不存在：{data_path}", bg=COLORS["surface"], fg="#B91C1C").pack(anchor=tk.W)
            return
        summary = summarize_csv(data_path)
        summary_card = self._card(self.content, 14, COLORS["surface_soft"])
        summary_card.pack(fill=tk.X, pady=(0, 14))
        tk.Label(summary_card, text=f"{summary['row_count']:,}", bg=COLORS["surface_soft"], fg=COLORS["sidebar"], font=("Microsoft YaHei UI", 18, "bold")).pack(side=tk.LEFT, padx=(0, 38))
        tk.Label(summary_card, text="样本行数", bg=COLORS["surface_soft"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT, padx=(0, 24))
        tk.Label(summary_card, text=f"{summary['session_count']} 个独立会话    {len(summary['headers'])} 个字段", bg=COLORS["surface_soft"], fg=COLORS["text"], font=("Microsoft YaHei UI", 10)).pack(side=tk.LEFT)
        table_card = self._card(self.content, 12)
        table_card.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(table_card, columns=summary["headers"], show="headings", height=17)
        for heading in summary["headers"]:
            tree.heading(heading, text=heading)
            tree.column(heading, width=130, stretch=True)
        for row in summary["preview"]:
            tree.insert("", tk.END, values=[row.get(heading, "") for heading in summary["headers"]])
        tree.pack(fill=tk.BOTH, expand=True)

    def show_training(self) -> None:
        self._set_active_page("training")
        self._clear_content()
        self._title("训练方案", "调整参数后启动新的独立实验；历史训练和结果不会被覆盖。")
        if not self._require_paths():
            return
        if not self.training_ready():
            warning = self._card(self.content, 14, "#FFF7E6")
            warning.pack(fill=tk.X)
            tk.Label(warning, text="环境尚未初始化", bg="#FFF7E6", fg=COLORS["warning"], font=("Microsoft YaHei UI", 11, "bold")).pack(anchor=tk.W)
            tk.Label(warning, text="请先运行“初始化环境.bat”，然后重新启动平台。", bg="#FFF7E6", fg=COLORS["warning"], font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, pady=(4, 0))
            return
        if self.project is not None and self.project.name == "NASA 五状态（改进）":
            self._show_lifecycle_training_form()
            return
        custom_state: tuple[dict, dict] | None = None
        try:
            custom_state = self._custom_project_state()
        except ValueError:
            pass
        defaults = self.default_settings_for(self.project.name if self.project is not None else "A123 SOC")
        self.setting_vars = {
            "window": tk.IntVar(value=defaults["window"]), "epochs": tk.IntVar(value=defaults["epochs"]),
            "max_train": tk.IntVar(value=defaults["max_train"]), "max_valid": tk.IntVar(value=defaults["max_valid"]),
            "max_test": tk.IntVar(value=defaults["max_test"]), "hidden": tk.IntVar(value=defaults["hidden"]),
            "learning_rate": tk.DoubleVar(value=defaults["learning_rate"]), "seed": tk.IntVar(value=defaults["seed"]),
            "patience": tk.IntVar(value=defaults["patience"]), "dropout": tk.DoubleVar(value=defaults["dropout"]),
            "weight_decay": tk.DoubleVar(value=defaults["weight_decay"]), "lr_patience": tk.IntVar(value=defaults["lr_patience"]),
            "lr_factor": tk.DoubleVar(value=defaults["lr_factor"]), "min_learning_rate": tk.DoubleVar(value=defaults["min_learning_rate"]),
            "min_delta": tk.DoubleVar(value=defaults["min_delta"]), "gradient_clip": tk.DoubleVar(value=defaults["gradient_clip"]),
            "add_delta_ah": tk.BooleanVar(value=True), "balance_soc": tk.BooleanVar(value=True),
        }
        if custom_state is not None:
            custom_config, custom_admission = custom_state
            config_card = self._card(self.content, 16, COLORS["surface_soft"])
            config_card.pack(fill=tk.X, pady=(0, 14))
            tk.Label(
                config_card,
                text="自定义电池算法配置",
                bg=COLORS["surface_soft"],
                fg=COLORS["text"],
                font=("Microsoft YaHei UI", 12, "bold"),
            ).pack(anchor=tk.W)
            targets = tuple(str(item) for item in custom_config.get("target_columns", ()))
            roles = tuple(tuple(item) for item in custom_config.get("role_columns", ()))
            role_text = "，".join(f"{role}←{source}" for role, source in roles) or "未映射"
            tk.Label(
                config_card,
                text=f"预测目标：{', '.join(targets)}\n字段角色：{role_text}",
                bg=COLORS["surface_soft"],
                fg=COLORS["muted"],
                justify=tk.LEFT,
                wraplength=760,
            ).pack(anchor=tk.W, pady=(5, 10))
            algorithm_row = tk.Frame(config_card, bg=COLORS["surface_soft"])
            algorithm_row.pack(fill=tk.X)
            self.custom_algorithm_var = tk.StringVar(value=str(custom_config["algorithm"]))
            ttk.Combobox(
                algorithm_row,
                textvariable=self.custom_algorithm_var,
                values=algorithm_keys(),
                state="readonly",
                width=18,
            ).pack(side=tk.LEFT)
            ttk.Button(
                algorithm_row,
                text="保存算法配置",
                style="Secondary.TButton",
                command=self._save_custom_algorithm,
            ).pack(side=tk.LEFT, padx=(10, 0))
            self.custom_recommendation_text = tk.StringVar(
                value=f"建议：{recommend_algorithm(targets)}（仅建议，不授予训练权限）"
            )
            tk.Label(
                config_card,
                textvariable=self.custom_recommendation_text,
                bg=COLORS["surface_soft"],
                fg=COLORS["muted"],
            ).pack(anchor=tk.W, pady=(8, 0))
            self.custom_admission_text = tk.StringVar(
                value=self._custom_admission_summary(custom_admission)
            )
            tk.Label(
                config_card,
                textvariable=self.custom_admission_text,
                bg=COLORS["surface_soft"],
                fg=COLORS["warning"],
                wraplength=760,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=(5, 0))
        form_card = self._card(self.content, 16)
        self.training_form_card = form_card
        form_card.pack(fill=tk.X)
        form = ttk.LabelFrame(form_card, text="Training parameters · 训练参数", style="Card.TLabelframe", padding=14)
        form.pack(fill=tk.X)
        fields = (
            ("连续时间窗口", "window"), ("最大训练轮数", "epochs"),
            ("训练样本上限", "max_train"), ("验证样本上限", "max_valid"),
            ("测试样本上限", "max_test"), ("隐藏层大小", "hidden"),
            ("学习率", "learning_rate"), ("随机种子", "seed"),
        )
        for index, (label, key) in enumerate(fields):
            row, column = divmod(index, 2)
            ttk.Label(form, text=label).grid(row=row, column=column * 2, sticky=tk.W, padx=(0, 8), pady=6)
            ttk.Entry(form, textvariable=self.setting_vars[key], width=16).grid(row=row, column=column * 2 + 1, sticky=tk.W, padx=(0, 28), pady=6)
        ttk.Checkbutton(form, text="加入窗口 Ah 特征", variable=self.setting_vars["add_delta_ah"]).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(10, 2))
        ttk.Checkbutton(form, text="按 SOC 区间均衡训练样本", variable=self.setting_vars["balance_soc"]).grid(row=4, column=2, columnspan=2, sticky=tk.W, pady=(10, 2))
        advanced = ttk.LabelFrame(form_card, text="Advanced regularization · 防过拟合设置", style="Card.TLabelframe", padding=14)
        advanced.pack(fill=tk.X, pady=(14, 0))
        advanced_fields = (
            ("Dropout 比例", "dropout"), ("权重衰减", "weight_decay"),
            ("早停耐心轮数", "patience"), ("学习率调整耐心轮数", "lr_patience"),
            ("学习率衰减系数", "lr_factor"), ("最小学习率", "min_learning_rate"),
            ("最小有效改进", "min_delta"), ("梯度裁剪上限", "gradient_clip"),
        )
        for index, (label, key) in enumerate(advanced_fields):
            row, column = divmod(index, 2)
            ttk.Label(advanced, text=label).grid(row=row, column=column * 2, sticky=tk.W, padx=(0, 8), pady=6)
            ttk.Entry(advanced, textvariable=self.setting_vars[key], width=16).grid(row=row, column=column * 2 + 1, sticky=tk.W, padx=(0, 28), pady=6)
        risk = tk.Frame(form_card, bg="#FFF7E6", padx=12, pady=9)
        risk.pack(fill=tk.X, pady=(14, 10))
        tk.Label(risk, text="提示：每次运行都会创建新的结果目录，已有模型、图表与训练记录不会被覆盖。", bg="#FFF7E6", fg=COLORS["warning"], font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W)
        self.start_button = ttk.Button(form_card, text="开始新的训练", style="Accent.TButton", command=self.start_training)
        self.start_button.pack(anchor=tk.W)
        self.progress_frame = self._card(self.content, 10, COLORS["surface_soft"])
        if self.progress_value is None:
            self.progress_value = tk.DoubleVar(value=self.training_progress_display)
        if self.progress_text is None:
            self.progress_text = tk.StringVar(value=f"正在训练：{int(self.training_progress_target)}%")
        tk.Label(self.progress_frame, textvariable=self.progress_text, bg=COLORS["surface"], fg=COLORS["text"], font=("Microsoft YaHei UI", 9, "bold")).pack(anchor=tk.W, pady=(0, 5))
        ttk.Progressbar(self.progress_frame, style="Training.Horizontal.TProgressbar", mode="determinate", maximum=100, variable=self.progress_value).pack(fill=tk.X)
        log_card = self._card(self.content, 12)
        log_card.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        tk.Label(log_card, text="训练日志", bg=COLORS["surface"], fg=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 8))
        self.log_text = tk.Text(log_card, height=13, state=tk.DISABLED, wrap=tk.WORD, borderwidth=0, bg="#F8F7FC", fg=COLORS["text"], font=("Consolas", 9), padx=10, pady=9)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        if self.training_log_buffer:
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, self.training_log_buffer)
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        if custom_state is not None and custom_state[1].get("training_allowed") is not True:
            self._set_start_enabled(False)
        elif self.controller.status() == "running":
            self._set_progress_visible(True)
            self._set_start_enabled(False)

    def _show_lifecycle_training_form(self) -> None:
        """Render the small, experiment-safe control set for the lifecycle suite."""
        defaults = self.default_settings_for("NASA 五状态（改进）")
        self.setting_vars = {
            "stage": tk.StringVar(value=str(defaults["stage"])),
            "seed": tk.IntVar(value=int(defaults["seed"])),
        }
        form_card = self._card(self.content, 16)
        self.training_form_card = form_card
        form_card.pack(fill=tk.X)
        tk.Label(form_card, text="NASA 五状态（改进）", bg=COLORS["surface"], fg=COLORS["text"], font=("Microsoft YaHei UI", 13, "bold")).pack(anchor=tk.W)
        tk.Label(form_card, text="四电芯留一验证：SOH、RUL、SOC、SOE 与未来 5 分钟温度。旧 NASA 五状态基线不会被修改。", bg=COLORS["surface"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9), wraplength=760, justify=tk.LEFT).pack(anchor=tk.W, pady=(5, 14))
        form = ttk.LabelFrame(form_card, text="实验设置", style="Card.TLabelframe", padding=14)
        form.pack(fill=tk.X)
        ttk.Label(form, text="训练阶段").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=6)
        ttk.Combobox(form, textvariable=self.setting_vars["stage"], values=("smoke", "formal"), state="readonly", width=14).grid(row=0, column=1, sticky=tk.W, padx=(0, 28), pady=6)
        ttk.Label(form, text="随机种子").grid(row=0, column=2, sticky=tk.W, padx=(0, 8), pady=6)
        ttk.Entry(form, textvariable=self.setting_vars["seed"], width=16).grid(row=0, column=3, sticky=tk.W, pady=6)
        tk.Label(form_card, text="smoke 仅检查完整流程；formal 运行完整四折训练。种子 42 使用默认目录，其他种子使用独立目录。", bg=COLORS["surface"], fg=COLORS["warning"], font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, pady=(12, 10))
        self.start_button = ttk.Button(form_card, text="开始五状态泛化实验", style="Accent.TButton", command=self.start_training)
        self.start_button.pack(anchor=tk.W)
        self.progress_frame = self._card(self.content, 10, COLORS["surface_soft"])
        self.progress_value = tk.DoubleVar(value=self.training_progress_display)
        self.progress_text = tk.StringVar(value="正在训练：0%")
        tk.Label(self.progress_frame, textvariable=self.progress_text, bg=COLORS["surface"], fg=COLORS["text"], font=("Microsoft YaHei UI", 9, "bold")).pack(anchor=tk.W, pady=(0, 5))
        ttk.Progressbar(self.progress_frame, style="Training.Horizontal.TProgressbar", mode="indeterminate").pack(fill=tk.X)
        log_card = self._card(self.content, 12)
        log_card.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        tk.Label(log_card, text="训练日志", bg=COLORS["surface"], fg=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 8))
        self.log_text = tk.Text(log_card, height=13, state=tk.DISABLED, wrap=tk.WORD, borderwidth=0, bg="#F8F7FC", fg=COLORS["text"], font=("Consolas", 9), padx=10, pady=9)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def start_training(self) -> None:
        if self.project is None:
            return
        settings = {key: variable.get() for key, variable in self.setting_vars.items()}
        custom_admission: dict | None = None
        try:
            if self.store is not None:
                try:
                    self.store.custom_config_for(self.project)
                except ValueError:
                    command_builder = None
                else:
                    _, custom_admission = self._custom_project_state()
                    command_builder = build_custom_command
            else:
                command_builder = None
            if command_builder is not None:
                pass
            elif self.project.name == "NASA 五状态（改进）":
                command_builder = build_hybrid_command
            elif self.project.name == "NASA 五状态":
                command_builder = build_multistate_command
            else:
                command_builder = build_soc_command
            command, run_dir = command_builder(self.project, settings, resolve_training_python(self.project_root))
            if custom_admission is None:
                self.controller.start(command, run_dir, self.project_root)
            else:
                self.controller.start(
                    command,
                    run_dir,
                    self.project_root,
                    admission=custom_admission,
                )
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            messagebox.showerror("无法开始训练", str(error))
            return
        self.current_run = run_dir
        self.training_epochs = int(settings.get("epochs", 1))
        self.training_log_buffer = ""
        if self._widget_exists(self.log_text):
            assert self.log_text is not None
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.delete("1.0", tk.END)
            self.log_text.configure(state=tk.DISABLED)
        self.training_progress_target = 0.0
        self.training_progress_display = 0.0
        if self.progress_value is not None:
            self.progress_value.set(0)
        if self.progress_text is not None:
            self.progress_text.set("正在训练：0%")
        self._set_progress_visible(True)
        self._set_start_enabled(False)
        self._append_log("开始训练：\n" + " ".join(command) + "\n\n")
        self._refresh_training_output()

    def _append_log(self, text: str) -> None:
        self.training_log_buffer += text
        if not self._widget_exists(self.log_text):
            return
        assert self.log_text is not None
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _refresh_training_output(self) -> None:
        for line in self.controller.poll():
            self._append_log(line)
            progress = epoch_progress(line, self.training_epochs)
            if progress is not None:
                self._set_progress_target(progress)
        if self.controller.status() == "running":
            assert self.root is not None
            self.root.after(200, self._refresh_training_output)
            return
        if self.current_run is not None:
            self._append_log(f"\n训练状态：{self.controller.status()}\n结果目录：{self.current_run}\n")
            if self.controller.status() == "succeeded":
                self._set_progress_target(100)
                if self.project is not None and self.project.name == "NASA 五状态":
                    build_multistate_charts(self.current_run)
                elif self.project is not None and self.project.name == "NASA 五状态（改进）":
                    build_hybrid_charts(self.current_run)
                elif self.project is not None:
                    ensure_run_charts(self.current_run)
        self._set_progress_visible(False)
        self._set_start_enabled(True)

    def _show_lifecycle_results(self) -> None:
        """Render the newest complete hybrid run."""
        assert self.project is not None
        runs = sorted((path for path in (self.project.path / "runs").iterdir() if path.is_dir()), reverse=True)
        formal_dir = self.current_run if self.current_run is not None else (runs[0] if runs else self.project.path / "runs" / "missing")
        try:
            result = read_hybrid_result(formal_dir)
        except ValueError as error:
            card = self._card(self.content, 16, "#FFF7E6")
            card.pack(fill=tk.X)
            tk.Label(card, text="改进五状态结果不可用", bg="#FFF7E6", fg=COLORS["warning"], font=("Microsoft YaHei UI", 11, "bold")).pack(anchor=tk.W)
            tk.Label(card, text=str(error), bg="#FFF7E6", fg=COLORS["warning"], font=("Microsoft YaHei UI", 9), wraplength=760, justify=tk.LEFT).pack(anchor=tk.W, pady=(5, 0))
            return
        summary_card = self._card(self.content, 14, COLORS["surface_soft"])
        summary_card.pack(fill=tk.X, pady=(0, 14))
        status = "已验证：旧五状态基线未变更" if result["baseline_hash_verified"] else "警告：旧五状态基线哈希不一致"
        tk.Label(summary_card, text="NASA 五状态（改进）· 四折 LOCO 结果", bg=COLORS["surface_soft"], fg=COLORS["text"], font=("Microsoft YaHei UI", 12, "bold")).pack(anchor=tk.W)
        tk.Label(summary_card, text=status, bg=COLORS["surface_soft"], fg=COLORS["success"] if result["baseline_hash_verified"] else COLORS["warning"], font=("Microsoft YaHei UI", 9, "bold")).pack(anchor=tk.W, pady=(5, 0))
        table_card = self._card(self.content, 12)
        table_card.pack(fill=tk.X, pady=(0, 14))
        tree = ttk.Treeview(table_card, columns=("target", "mae", "rmse"), show="headings", height=5)
        tree.heading("target", text="目标")
        tree.heading("mae", text="平均 MAE")
        tree.heading("rmse", text="平均 RMSE")
        for column, width in (("target", 160), ("mae", 180), ("rmse", 180)):
            tree.column(column, width=width, stretch=True)
        for target in ("soc", "soe", "soh", "rul_cycles", "sot_5min_c"):
            metric = result["metrics"][target]
            tree.insert("", tk.END, values=(target, f"{float(metric['mean_MAE']):.6f}", f"{float(metric['mean_RMSE']):.6f}"))
        tree.pack(fill=tk.X)
        charts = build_hybrid_charts(formal_dir)
        for target, label in (("soc", "SOC"), ("soe", "SOE"), ("soh", "SOH"), ("rul_cycles", "RUL"), ("sot_5min_c", "SOT")):
            chart_card = self._card(self.content, 12)
            chart_card.pack(fill=tk.BOTH, expand=True, pady=(0, 14))
            tk.Label(chart_card, text=f"四个未见电芯 · {label} 预测对比", bg=COLORS["surface"], fg=COLORS["text"], font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))
            self._show_chart(chart_card, charts[target])
        fold_card = self._card(self.content, 12)
        fold_card.pack(fill=tk.X, pady=(0, 14))
        tk.Label(fold_card, text="独立测试电芯：" + "、".join(str(name) for name in result["folds"]), bg=COLORS["surface"], fg=COLORS["text"], font=("Microsoft YaHei UI", 10)).pack(anchor=tk.W)
        actions = tk.Frame(self.content, bg=COLORS["surface"])
        actions.pack(anchor=tk.W)
        report_path = result["report_path"]
        ttk.Button(actions, text="打开正式报告", style="Secondary.TButton", command=lambda: os.startfile(str(report_path)) if report_path.is_file() else None).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(actions, text="打开结果文件夹", style="Secondary.TButton", command=lambda: os.startfile(str(formal_dir)) if formal_dir.is_dir() else None).pack(side=tk.LEFT)

    def show_results(self) -> None:
        self._set_active_page("results")
        self._clear_content()
        self._title("实验结果", "选择历史实验查看评估指标、预测对比图、验证损失曲线和完整日志。")
        if not self._require_paths():
            return
        assert self.project is not None
        if self.project.name == "NASA 五状态（改进）":
            self._show_lifecycle_results()
            return
        generalization_summary = self.paths.generalization_results_dir / "formal" / "generalization_summary.json"
        if generalization_summary.is_file():
            try:
                summary = read_generalization_summary(generalization_summary)
            except (OSError, ValueError, json.JSONDecodeError):
                summary = None
            if summary is not None:
                summary_card = self._card(self.content, 12, COLORS["surface_soft"])
                summary_card.pack(fill=tk.X, pady=(0, 12))
                tk.Label(
                    summary_card,
                    text="综合泛化验证（只读）",
                    bg=COLORS["surface_soft"],
                    fg=COLORS["text"],
                    font=("Microsoft YaHei UI", 11, "bold"),
                ).pack(anchor=tk.W)
                tk.Label(
                    summary_card,
                    text=(
                        f"五种子平均 MAE：{summary['seed_mean_MAE_pct']}   "
                        f"留一工况最差 MAE：{summary['loso_worst_MAE_pct']}   "
                        f"A123#5 MAE：{summary['A1235_MAE_pct']}   "
                        f"结论：{summary['decision']}"
                    ),
                    bg=COLORS["surface_soft"],
                    fg=COLORS["muted"],
                    font=("Microsoft YaHei UI", 9),
                ).pack(anchor=tk.W, pady=(5, 0))
        runs = sorted((self.project.path / "runs").glob("*"), reverse=True)
        if not runs:
            empty = self._card(self.content, 16, COLORS["surface_soft"])
            empty.pack(fill=tk.X)
            tk.Label(empty, text="尚未从平台启动训练。", bg=COLORS["surface_soft"], fg=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold")).pack(anchor=tk.W)
            tk.Label(empty, text="请转到“训练方案”页开始新的独立实验。", bg=COLORS["surface_soft"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, pady=(5, 0))
            return
        body = tk.Frame(self.content, bg=COLORS["surface"])
        body.pack(fill=tk.BOTH, expand=True)
        list_card = self._card(body, 10)
        list_card.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 14))
        tk.Label(list_card, text="历史实验", bg=COLORS["surface"], fg=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold")).pack(anchor=tk.W, pady=(0, 8))
        run_list = tk.Listbox(list_card, height=20, width=27, borderwidth=0, highlightthickness=0, bg="#F8F7FC", fg=COLORS["text"], selectbackground=COLORS["sidebar"], selectforeground="#FFFFFF", font=("Microsoft YaHei UI", 9), activestyle="none")
        for run in runs:
            run_list.insert(tk.END, run.name)
        run_list.pack(fill=tk.Y, expand=True)
        result_card = self._card(body, 10)
        result_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tabs = ttk.Notebook(result_card)
        detail_tab = tk.Frame(tabs, bg=COLORS["surface"], padx=10, pady=10)
        prediction_tab = tk.Frame(tabs, bg=COLORS["surface"], padx=10, pady=10)
        loss_tab = tk.Frame(tabs, bg=COLORS["surface"], padx=10, pady=10)
        tabs.add(detail_tab, text="指标与日志")
        tabs.add(prediction_tab, text="SOC 预测对比图")
        tabs.add(loss_tab, text="验证损失曲线")
        multistate_chart_tabs: dict[str, tk.Frame] = {}
        is_multistate_project = self.project is not None and self.project.name == "NASA 五状态"
        if is_multistate_project:
            tabs.forget(loss_tab)
            for target in ("soh", "soe", "rul_cycles", "sot_c"):
                tab = tk.Frame(tabs, bg=COLORS["surface"], padx=10, pady=10)
                multistate_chart_tabs[target] = tab
                tabs.add(tab, text=target.upper())
        detail = tk.Text(detail_tab, height=20, state=tk.DISABLED, wrap=tk.WORD, borderwidth=0, bg="#F8F7FC", fg=COLORS["text"], font=("Consolas", 9), padx=12, pady=10)
        detail.pack(fill=tk.BOTH, expand=True)
        tabs.pack(fill=tk.BOTH, expand=True)

        def show_selected(_: object = None) -> None:
            selection = run_list.curselection()
            if not selection:
                return
            result = read_run_result(runs[selection[0]])
            is_multistate = is_multistate_project
            chart_paths = build_multistate_charts(result.path) if is_multistate else ensure_run_charts(result.path)
            chart_frames = [prediction_tab, loss_tab, *multistate_chart_tabs.values()]
            for child in [child for frame in chart_frames for child in frame.winfo_children()]:
                child.destroy()
            self._show_chart(prediction_tab, chart_paths.get("soc") if is_multistate else chart_paths.get("prediction"))
            if is_multistate:
                for target, tab in multistate_chart_tabs.items():
                    self._show_chart(tab, chart_paths.get(target))
            else:
                self._show_chart(loss_tab, chart_paths.get("validation_loss"))
            chunks = [f"状态：{result.status}\n", json.dumps(result.metrics or {}, ensure_ascii=False, indent=2)]
            if is_multistate:
                chunks.append("\n\n" + (result.path / "metrics_by_target.json").read_text(encoding="utf-8"))
            if result.log_path:
                chunks.append("\n\n" + result.log_path.read_text(encoding="utf-8", errors="replace")[-4000:])
            detail.configure(state=tk.NORMAL)
            detail.delete("1.0", tk.END)
            detail.insert(tk.END, "".join(chunks))
            detail.configure(state=tk.DISABLED)

        def delete_selected() -> None:
            selection = run_list.curselection()
            if not selection:
                return
            selected_run = runs[selection[0]]
            if (
                self.controller.status() == "running"
                and self.current_run is not None
                and selected_run.resolve() == self.current_run.resolve()
            ):
                messagebox.showwarning("无法删除", "正在训练的实验不能删除。")
                return
            expression, expected_answer = deletion_math_challenge()
            answer = simpledialog.askinteger(
                "永久删除训练结果",
                "警告：此操作会永久删除该实验的模型、指标、图表、预测和日志，无法恢复。\n\n"
                f"实验编号：{selected_run.name}\n\n"
                f"请输入计算结果以确认删除：\n{expression} = ?",
                parent=self.root,
            )
            if answer is None:
                return
            if answer != expected_answer:
                messagebox.showerror("答案错误", "计算结果不正确，已取消删除。")
                return
            assert self.store is not None and self.project is not None
            try:
                self.store.delete_run(self.project.project_id, selected_run.name, selected_run.name)
            except ValueError as error:
                messagebox.showerror("删除失败", str(error))
                return
            messagebox.showinfo("删除完成", f"训练结果已永久删除：\n{selected_run.name}")
            self.show_results()

        context_menu = tk.Menu(run_list, tearoff=False)
        context_menu.add_command(label="永久删除训练结果…", command=delete_selected)

        def show_context_menu(event: tk.Event) -> None:
            index = run_list.nearest(event.y)
            bounds = run_list.bbox(index)
            if bounds is None or not (bounds[1] <= event.y <= bounds[1] + bounds[3]):
                return
            run_list.selection_clear(0, tk.END)
            run_list.selection_set(index)
            run_list.activate(index)
            show_selected()
            try:
                context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                context_menu.grab_release()

        run_list.bind("<<ListboxSelect>>", show_selected)
        run_list.bind("<Button-3>", show_context_menu)
        run_list.selection_set(0)
        show_selected()


def main() -> None:
    root = tk.Tk()
    project_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
    DesktopTrainingApp(root, project_root)
    root.mainloop()


if __name__ == "__main__":
    main()
