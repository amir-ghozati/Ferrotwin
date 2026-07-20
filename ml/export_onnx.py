from pathlib import Path

import torch
import torch.nn as nn
from torchvision import models

MODEL_PATH = Path("../models/best_model.pth")
ONNX_PATH = Path("../models/best_model.onnx")

NUM_CLASSES = 6

device = torch.device("cpu")

# همان معماری آموزش
model = models.resnet18(weights=None)
model.fc = nn.Linear(model.fc.in_features, NUM_CLASSES)

model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
model.eval()

dummy_input = torch.randn(1, 3, 224, 224)

torch.onnx.export(
    model,
    dummy_input,
    ONNX_PATH,
    export_params=True,
    opset_version=17,
    do_constant_folding=True,
    input_names=["input"],
    output_names=["output"],
    dynamic_axes={
        "input": {0: "batch"},
        "output": {0: "batch"},
    },
)

print(f"ONNX model saved to {ONNX_PATH}")