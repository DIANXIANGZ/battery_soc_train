from __future__ import annotations
import unittest
import numpy as np
from src.training.battery_protocol import acceptance, fit_normalizer
class ProtocolTests(unittest.TestCase):
 def test_normalizer_uses_training_values_only(self):
  mean,std=fit_normalizer(np.array([[1.,2.],[3.,4.]])); self.assertTrue(np.allclose(mean,[2.,3.])); self.assertTrue(np.allclose(std,[1.,1.]))
 def test_thresholds_are_target_specific(self):
  self.assertTrue(acceptance("soc",.009,np.array([.5]))["passed"]); self.assertFalse(acceptance("rul_cycles",1.1,np.array([20.]))["passed"])
