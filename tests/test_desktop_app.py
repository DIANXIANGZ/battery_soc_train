from __future__ import annotations

import tempfile
import unittest
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.custom_training.dataset import CustomDatasetConfig
from src.desktop.app import DesktopTrainingApp, deletion_math_challenge
from src.platform.platform_core import PlatformStore


class DesktopTrainingAppTests(unittest.TestCase):
    def test_custom_state_exposes_generalization_and_per_target_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.csv"
            source.write_text(
                "time,cell,condition,voltage,current,soc\n"
                + "\n".join(
                    f"{index},c{index % 4},k{index % 2},3.7,1.0,0.8" for index in range(40)
                ),
                encoding="utf-8",
            )
            app = DesktopTrainingApp.create_for_test(root)
            store = PlatformStore(root / "store")
            project = store.create_custom_project(
                "blocked-details",
                CustomDatasetConfig(
                    source,
                    None,
                    "time",
                    ("voltage", "current"),
                    ("soc",),
                    "lstm",
                    role_columns=(("cell_id", "cell"), ("condition_id", "condition")),
                ),
                Path(__file__).resolve().parents[1] / "src" / "training" / "train_custom.py",
            )
            app.store = store
            app.project = project

            _, admission = app._custom_project_state()
            summary = app._custom_admission_summary(admission)

            self.assertIn("unseen_cell_and_condition", summary)
            self.assertIn("soc", summary)
            self.assertIn("missing_role:session_id", summary)
            self.assertIn("causal_label_audit_missing", summary)

    def test_custom_training_page_exposes_algorithm_config_but_disables_run_when_blocked(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display is unavailable: {error}")
        try:
            root.geometry("1180x760+5000+5000")
            app = DesktopTrainingApp(root, project_root)
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_root = Path(temp_dir)
                source = temp_root / "source.csv"
                source.write_text(
                    "time,voltage,current,soc\n"
                    + "\n".join(f"{index},3.7,1.0,0.8" for index in range(40)),
                    encoding="utf-8",
                )
                store = PlatformStore(temp_root / "store")
                project = store.create_custom_project(
                    "blocked",
                    CustomDatasetConfig(source, None, "time", ("voltage", "current"), ("soc",), "lstm"),
                    project_root / "src" / "training" / "train_custom.py",
                )
                app.store = store
                app.project = project
                app.projects = {project.name: project}
                app.paths = SimpleNamespace()
                app.training_ready = lambda: True

                app.show_training()
                root.update()

                self.assertEqual(app.custom_algorithm_var.get(), "lstm")
                self.assertEqual(str(app.start_button.cget("state")), "disabled")
                self.assertIn("数据准入门禁", app.custom_admission_text.get())
        finally:
            root.destroy()

    def test_blocked_custom_start_never_calls_controller(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.csv"
            source.write_text(
                "time,voltage,current,soc\n"
                + "\n".join(f"{index},3.7,1.0,0.8" for index in range(40)),
                encoding="utf-8",
            )
            app = DesktopTrainingApp.create_for_test(root)
            store = PlatformStore(root / "store")
            project = store.create_custom_project(
                "blocked",
                CustomDatasetConfig(source, None, "time", ("voltage", "current"), ("soc",), "gru"),
                Path(__file__).resolve().parents[1] / "src" / "training" / "train_custom.py",
            )
            app.store = store
            app.project = project
            app.projects = {project.name: project}
            app.setting_vars = {}
            app.controller = Mock()

            with patch("src.desktop.app.messagebox.showerror"):
                app.start_training()

            app.controller.start.assert_not_called()

    def test_missing_custom_admission_never_falls_back_to_soc_training(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.csv"
            source.write_text(
                "time,voltage,current,soc\n"
                + "\n".join(f"{index},3.7,1.0,0.8" for index in range(40)),
                encoding="utf-8",
            )
            app = DesktopTrainingApp.create_for_test(root)
            store = PlatformStore(root / "store")
            project = store.create_custom_project(
                "missing-admission",
                CustomDatasetConfig(source, None, "time", ("voltage", "current"), ("soc",), "gru"),
                Path(__file__).resolve().parents[1] / "src" / "training" / "train_custom.py",
            )
            store._replace_record(project.project_id, custom_admission=None)
            app.store = store
            app.project = project
            app.projects = {project.name: project}
            app.setting_vars = {}
            app.controller = Mock()
            runs = project.path / "runs"
            before = tuple(runs.iterdir())

            with patch("src.desktop.app.messagebox.showerror"):
                app.start_training()

            app.controller.start.assert_not_called()
            self.assertEqual(tuple(runs.iterdir()), before)
    def test_custom_target_algorithm_recommendations_are_predictable(self) -> None:
        self.assertEqual(DesktopTrainingApp._recommended_algorithm(("soc",)), "lstm")
        self.assertEqual(DesktopTrainingApp._recommended_algorithm(("SOE", "sot")), "lstm")
        self.assertEqual(DesktopTrainingApp._recommended_algorithm(("rul_cycles",)), "xgboost")

    def test_desktop_source_exposes_custom_import_and_command_route(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "desktop" / "app.py").read_text(encoding="utf-8")
        self.assertIn("自定义数据集…", source)
        self.assertIn("build_custom_command", source)
        self.assertIn("Transformer", source)

    def test_original_nasa_five_state_is_excluded_from_project_selector(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "desktop" / "app.py").read_text(encoding="utf-8")
        self.assertIn('project.name != "NASA 五状态"', source)

    def test_legacy_nasa_lifecycle_project_is_excluded_from_project_selector(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "desktop" / "app.py").read_text(encoding="utf-8")
        self.assertIn('project.name not in {"NASA 五状态", "NASA 生命周期模型"}', source)

    def test_improved_nasa_results_render_all_five_target_charts(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "desktop" / "app.py").read_text(encoding="utf-8")
        self.assertIn('("soc", "SOC")', source)
        self.assertIn('("sot_5min_c", "SOT")', source)
        self.assertIn("self._show_chart(chart_card, charts[target])", source)

    def test_desktop_shell_keeps_a_fixed_sidebar_and_roomy_content(self) -> None:
        project = Path(__file__).resolve().parents[1]
        source = (project / "src" / "desktop" / "app.py").read_text(encoding="utf-8")

        self.assertIn("width=236", source)
        self.assertIn("padx=36, pady=30", source)

    def test_overview_is_empty_when_runs_have_no_complete_data(self) -> None:
        project = Path(__file__).resolve().parents[1]
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display is unavailable: {error}")
        try:
            root.geometry("1180x760+5000+5000")
            app = DesktopTrainingApp(root, project)
            with tempfile.TemporaryDirectory() as temp_dir:
                project_path = Path(temp_dir) / "project"
                (project_path / "runs" / "incomplete-run").mkdir(parents=True)
                app.project = SimpleNamespace(path=project_path)

                app.show_overview()
                root.update()

                def label_texts(widget: tk.Misc) -> list[str]:
                    texts: list[str] = []
                    for child in widget.winfo_children():
                        if isinstance(child, tk.Label):
                            texts.append(str(child.cget("text")))
                        texts.extend(label_texts(child))
                    return texts

                texts = label_texts(app.content)
                self.assertIn("暂无实验结果", texts)
                self.assertFalse(any("MAE" in text for text in texts))
                self.assertFalse(any("SOC 预测趋势" in text for text in texts))
        finally:
            root.destroy()

    def test_training_progress_is_mapped_at_default_window_size(self) -> None:
        project = Path(__file__).resolve().parents[1]
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display is unavailable: {error}")
        try:
            root.geometry("1180x760+5000+5000")
            app = DesktopTrainingApp(root, project)
            app.show_training()
            root.update()

            app._set_progress_visible(True)
            root.update()

            self.assertTrue(app.progress_frame.winfo_ismapped())
            self.assertGreater(app.progress_frame.winfo_width(), 1)
        finally:
            root.destroy()

    def test_training_content_scrolls_with_mouse_wheel_in_small_window(self) -> None:
        project = Path(__file__).resolve().parents[1]
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display is unavailable: {error}")
        try:
            root.geometry("1000x420+5000+5000")
            app = DesktopTrainingApp(root, project)
            app.show_training()
            root.update()

            before = app.content_canvas.yview()[0]
            app._on_content_mouse_wheel(SimpleNamespace(delta=-120, widget=app.content))
            root.update()

            self.assertGreater(app.content_canvas.yview()[0], before)
        finally:
            root.destroy()

    def test_scrollable_content_uses_the_confirmed_roomy_title_gutter(self) -> None:
        project = Path(__file__).resolve().parents[1]
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display is unavailable: {error}")
        try:
            app = DesktopTrainingApp(root, project)
            self.assertEqual(int(str(app.content.cget("padx"))), 36)
            self.assertEqual(int(str(app.content.cget("pady"))), 30)
        finally:
            root.destroy()

    def test_training_settings_match_the_soc_command_allowlist(self) -> None:
        self.assertEqual(
            DesktopTrainingApp.default_settings(),
            {
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
            },
        )

    def test_improved_five_state_defaults_expose_only_stage_and_seed(self) -> None:
        settings = DesktopTrainingApp.default_settings_for("NASA 五状态（改进）")

        self.assertEqual(settings, {"stage": "formal", "seed": 42})

    def test_results_page_has_lifecycle_reader_and_open_actions(self) -> None:
        project = Path(__file__).resolve().parents[1]
        source = (project / "src" / "desktop" / "app.py").read_text(encoding="utf-8")

        self.assertIn("read_hybrid_result", source)
        self.assertIn("打开正式报告", source)
        self.assertIn("打开结果文件夹", source)

    def test_missing_data_center_requires_configuration_before_training(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = DesktopTrainingApp.create_for_test(Path(temp_dir))

            self.assertFalse(app.training_ready())
            self.assertIn("数据中心", app.startup_message())

    def test_results_page_integrates_portable_chart_generation(self) -> None:
        project = Path(__file__).resolve().parents[1]
        source = (project / "src" / "desktop" / "app.py").read_text(encoding="utf-8")

        self.assertIn("ensure_run_charts", source)
        self.assertIn("validation_loss", source)
        self.assertIn("read_generalization_summary", source)
        self.assertIn("generalization_summary", source)

    def test_desktop_app_uses_the_warm_card_theme_without_changing_training_defaults(self) -> None:
        project = Path(__file__).resolve().parents[1]
        source = (project / "src" / "desktop" / "app.py").read_text(encoding="utf-8")

        self.assertIn("configure_theme", source)
        self.assertIn("Accent.TButton", source)
        self.assertIn("Training parameters", source)
        self.assertEqual(DesktopTrainingApp.default_settings()["window"], 60)

    def test_charts_use_the_interactive_viewer(self) -> None:
        project = Path(__file__).resolve().parents[1]
        source = (project / "src" / "desktop" / "app.py").read_text(encoding="utf-8")

        self.assertIn("InteractiveChartViewer", source)
        self.assertIn("滚轮缩放", source)

    def test_overview_starts_with_the_platform_banner(self) -> None:
        project = Path(__file__).resolve().parents[1]
        source = (project / "src" / "desktop" / "app.py").read_text(encoding="utf-8")

        self.assertNotIn('self._title("下午好，浩名"', source)

    def test_training_page_omits_the_task05_default_hint(self) -> None:
        project = Path(__file__).resolve().parents[1]
        source = (project / "src" / "desktop" / "app.py").read_text(encoding="utf-8")

        self.assertNotIn("任务05的防过拟合默认值已预填；不熟悉这些参数时，建议保持默认。", source)

    def test_training_page_shows_live_percentage_progress(self) -> None:
        project = Path(__file__).resolve().parents[1]
        source = (project / "src" / "desktop" / "app.py").read_text(encoding="utf-8")

        self.assertIn("正在训练：0%", source)
        self.assertIn("ttk.Progressbar", source)
        self.assertIn("epoch_progress", source)
        self.assertIn("self.progress_frame.pack(**pack_options)", source)
        self.assertIn('pack_options["before"] = self.training_form_card', source)
        self.assertIn("self.progress_frame.pack_forget()", source)
        self.assertIn('style="Training.Horizontal.TProgressbar"', source)
        self.assertIn("self.training_progress_target", source)
        self.assertIn("self.training_log_buffer", source)
        self.assertIn("self._animate_progress", source)
        self.assertIn('if self.controller.status() == "running":', source)

    def test_results_page_has_guarded_right_click_permanent_deletion(self) -> None:
        project = Path(__file__).resolve().parents[1]
        source = (project / "src" / "desktop" / "app.py").read_text(encoding="utf-8")

        self.assertIn('run_list.bind("<Button-3>"', source)
        self.assertIn("tk.Menu", source)
        self.assertIn("simpledialog.askinteger", source)
        self.assertNotIn("simpledialog.askstring", source)
        self.assertIn("计算结果不正确", source)
        self.assertIn("delete_run", source)
        self.assertIn("正在训练的实验不能删除", source)
        self.assertIn("永久删除", source)

    def test_delete_challenge_is_correct_and_stays_within_one_hundred(self) -> None:
        for _ in range(200):
            expression, answer = deletion_math_challenge()
            left_text, operator, right_text = expression.split()
            left, right = int(left_text), int(right_text)

            self.assertGreaterEqual(left, 0)
            self.assertLessEqual(left, 100)
            self.assertGreaterEqual(right, 0)
            self.assertLessEqual(right, 100)
            self.assertGreaterEqual(answer, 0)
            self.assertLessEqual(answer, 100)
            self.assertEqual(answer, left + right if operator == "+" else left - right)


if __name__ == "__main__":
    unittest.main()
