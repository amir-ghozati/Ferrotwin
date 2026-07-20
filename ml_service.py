from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image


MODEL_PATH = Path(__file__).parent / "models" / "best_model.onnx"

CLASSES = [
    "crazing",
    "inclusion",
    "patches",
    "pitted_surface",
    "rolled-in_scale",
    "scratches",
]


class MLService:

    def __init__(self):
        self.session = ort.InferenceSession(
            str(MODEL_PATH),
            providers=["CPUExecutionProvider"],
        )

        self.input_name = self.session.get_inputs()[0].name

    def preprocess(self, image_path):

        image = Image.open(image_path).convert("RGB")
        image = image.resize((224, 224))

        x = np.asarray(image).astype(np.float32) / 255.0

        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

        x = (x - mean) / std

        x = np.transpose(x, (2, 0, 1))

        x = np.expand_dims(x, axis=0)

        return x

    def predict(self, image_path):

        x = self.preprocess(image_path)

        outputs = self.session.run(
            None,
            {self.input_name: x},
        )

        logits = outputs[0][0]

        idx = int(np.argmax(logits))

        confidence = float(np.max(logits))

        return {
            "class": CLASSES[idx],
            "confidence": confidence,
        }
    