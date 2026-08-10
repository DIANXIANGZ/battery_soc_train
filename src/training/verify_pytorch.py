"""Run this file in PyCharm to verify the project PyTorch interpreter."""
import sys
import torch

print("Python interpreter:", sys.executable)
print("PyTorch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
print("PyTorch configuration verified.")
