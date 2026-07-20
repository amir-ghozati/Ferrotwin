"""ONNX inference for steel surface-defect classification.

Preprocessing is pure NumPy + Pillow and is a faithful reproduction of the
torchvision training transform:
    Resize((224, 224), bilinear) -> ToTensor (0..1) -> Normalize(ImageNet).
This removes the torch / torchvision dependency from the serving image, keeping
the Azure Functions deployment package small enough to publish.
"""

from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

CLASSES = [
    "crazing",
    "inclusion",
    "patches",
    "pitted_surface",
    "rolled-in_scale",
    "scratches",
]

MODEL_PATH = Path(__file__).parent / "models" / "best_model.onnx"

_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

session = ort.InferenceSession(
    str(MODEL_PATH),
    providers=["CPUExecutionProvider"],
)
_INPUT_NAME = session.get_inputs()[0].name


def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / e.sum()


def preprocess(image_path: str) -> np.ndarray:
    """Return a (1, 3, 224, 224) float32 tensor matching the training pipeline."""
    image = Image.open(image_path).convert("RGB")
    # torchvision.transforms.Resize default interpolation is bilinear.
    image = image.resize((224, 224), Image.BILINEAR)

    x = np.asarray(image, dtype=np.float32) / 255.0          # ToTensor: 0..1
    x = (x - _IMAGENET_MEAN) / _IMAGENET_STD                 # Normalize(ImageNet)
    x = np.transpose(x, (2, 0, 1))                           # HWC -> CHW
    return np.expand_dims(x, axis=0).astype(np.float32)


def predict(image_path: str) -> dict:
    tensor = preprocess(image_path)
    outputs = session.run(None, {_INPUT_NAME: tensor})[0]
    probs = softmax(outputs[0])
    idx = int(np.argmax(probs))
    return {
        "defect": CLASSES[idx],
        "confidence": float(probs[idx]),
    }
