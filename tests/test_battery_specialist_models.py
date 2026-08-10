from __future__ import annotations

import unittest

import numpy as np

from src.training.models.common import SpecialistDataset
from src.training.models.domain_adaptation import CoralAdapter
from src.training.models.rul import RULSpecialist
from src.training.models.soc import SOCSpecialist
from src.training.models.soe import SOESpecialist
from src.training.models.soh import SOHSpecialist
from src.training.models.sot import SOTResidualSpecialist
from src.training.models.sequence import TorchSequenceRegressor


def split_data() -> tuple[SpecialistDataset, SpecialistDataset]:
    x = np.arange(30, dtype=float).reshape(-1, 1) / 29
    y = 0.1 + 0.8 * x[:, 0]
    return SpecialistDataset(x[:20], y[:20]), SpecialistDataset(x[20:25], y[20:25])


class BatterySpecialistModelTests(unittest.TestCase):
    def test_soc_and_soe_predictions_are_bounded(self) -> None:
        train, validation = split_data()
        for specialist in (SOCSpecialist(), SOESpecialist()):
            with self.subTest(type=type(specialist).__name__):
                specialist.fit(train, validation)
                prediction = specialist.predict(np.array([[-100.0], [100.0]]))
                self.assertTrue(np.all((prediction >= 0) & (prediction <= 1)))
                self.assertIn("selected_by", specialist.artifact_manifest())

    def test_soh_prediction_is_monotonic_non_increasing(self) -> None:
        x = np.arange(30, dtype=float).reshape(-1, 1)
        y = 1.0 - 0.01 * x[:, 0]
        specialist = SOHSpecialist()
        specialist.fit(SpecialistDataset(x[:20], y[:20]), SpecialistDataset(x[20:25], y[20:25]))
        prediction = specialist.predict(x[25:])
        self.assertTrue(np.all(np.diff(prediction) <= 1e-12))

    def test_rul_prediction_is_not_capped_to_maximum_training_label(self) -> None:
        x = np.arange(10, dtype=float).reshape(-1, 1)
        y = 2.0 * x[:, 0]
        specialist = RULSpecialist()
        specialist.fit(SpecialistDataset(x[:7], y[:7]), SpecialistDataset(x[7:9], y[7:9]))
        prediction = specialist.predict(np.array([[20.0]]))
        self.assertGreater(float(prediction[0]), float(y[:7].max()))

    def test_rul_trajectory_uses_current_soh_and_causal_slope(self) -> None:
        features = np.array([
            [1.00, -0.001], [0.95, -0.001], [0.90, -0.001], [0.85, -0.001],
        ])
        target = np.array([200.0, 150.0, 100.0, 50.0])
        specialist = RULSpecialist(current_soh_index=0, slope_index=1)
        specialist.fit(SpecialistDataset(features[:3], target[:3]), SpecialistDataset(features[3:], target[3:]))
        prediction = specialist.predict(np.array([[0.82, -0.001]]))
        self.assertAlmostEqual(float(prediction[0]), 20.0, delta=1.0)
        self.assertEqual(specialist.artifact_manifest()["upper_label_clip"], False)

    def test_sot_models_temperature_rise_residual(self) -> None:
        x = np.column_stack([np.arange(20, dtype=float), np.full(20, 25.0)])
        y = 25.0 + 0.2 * x[:, 0]
        specialist = SOTResidualSpecialist(last_temperature_index=1)
        specialist.fit(SpecialistDataset(x[:14], y[:14]), SpecialistDataset(x[14:18], y[14:18]))
        prediction = specialist.predict(x[18:])
        self.assertTrue(np.all(prediction > 25.0))
        self.assertEqual(specialist.artifact_manifest()["prediction_form"], "last_temperature_plus_residual")

    def test_coral_uses_only_explicitly_allowed_domains(self) -> None:
        adapter = CoralAdapter()
        source = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
        allowed_target = np.array([[10.0, 10.0], [11.0, 11.0], [12.0, 12.0]])
        adapter.fit(source, allowed_target, source_keys=("train",), target_keys=("validation",))
        manifest = adapter.artifact_manifest()
        self.assertEqual(manifest["source_keys"], ["train"])
        self.assertEqual(manifest["target_keys"], ["validation"])
        self.assertEqual(adapter.transform(source).shape, source.shape)

    def test_literature_sequence_candidates_fit_causal_windows(self) -> None:
        values = np.arange(120, dtype=np.float32).reshape(20, 3, 2) / 120
        target = values[:, -1, 0]
        for kind in ("lstm", "gru", "tcn", "transformer"):
            with self.subTest(kind=kind):
                model = TorchSequenceRegressor(kind=kind, window=3, features=2, hidden=8, epochs=1, batch_size=20)
                model.fit(values.reshape(20, -1), target)
                prediction = model.predict(values[:2].reshape(2, -1))
                self.assertEqual(prediction.shape, (2,))
                self.assertTrue(np.isfinite(prediction).all())


if __name__ == "__main__":
    unittest.main()
