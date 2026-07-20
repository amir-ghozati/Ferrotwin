"""
FerroTwin - NEU-CLS surface defect classifier training
Run unattended overnight: python train.py

Outputs (written to OUTPUT_DIR):
  - best_model.pth         best checkpoint by validation accuracy
  - training_log.txt       per-epoch log, appended live (check this first if unsure it's working)
  - training_summary.json  final metrics + confusion matrix numbers
  - confusion_matrix.png
"""

import re
import json
import time
import random
from pathlib import Path
from datetime import datetime

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, models
from PIL import Image
from sklearn.metrics import confusion_matrix, classification_report
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------- CONFIG ----------------
# Point this at wherever you extracted the Kaggle zip. Everything under this
# folder is scanned recursively, so it's fine if there are extra nested folders.
DATA_ROOT = Path(r"D:\ADT\Neu-CLS")
OUTPUT_DIR = Path(r"D:\ADT\ml\output")

IMG_SIZE = 224
BATCH_SIZE = 32
HEAD_EPOCHS = 6          # phase 1: frozen backbone, train the new head only
FINE_TUNE_EPOCHS = 10    # phase 2: unfrozen, low learning rate
VAL_SPLIT = 0.2
SEED = 42
# -----------------------------------------

CLASSES = ["crazing", "inclusion", "patches", "pitted_surface", "rolled-in_scale", "scratches"]
CLASS_KEYWORDS = {
    "crazing": ["crazing", "cr"],
    "inclusion": ["inclusion", "in"],
    "patches": ["patches", "patch", "pa"],
    "pitted_surface": ["pitted", "pittedsurface", "ps"],
    "rolled-in_scale": ["rolled", "rolledinscale", "rs"],
    "scratches": ["scratches", "scratch", "sc"],
}

random.seed(SEED)
torch.manual_seed(SEED)


def log(msg: str):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(OUTPUT_DIR / "training_log.txt", "a") as f:
        f.write(line + "\n")


def infer_label(path: Path):
    """Try the parent folder name first (subfolder-per-class layout),
    then fall back to the filename prefix (flat layout, e.g. crazing_1.jpg)."""
    parent = re.sub(r"[\s_-]", "", path.parent.name.lower())
    for cls, keywords in CLASS_KEYWORDS.items():
        if parent in [re.sub(r"[\s_-]", "", k) for k in keywords] or parent == re.sub(r"[\s_-]", "", cls):
            return cls

    stem = path.stem.lower()
    token = re.split(r"[_\-\s]", stem)[0]
    for cls, keywords in CLASS_KEYWORDS.items():
        if token in keywords:
            return cls
    return None


def find_images(root: Path):
    exts = {".jpg", ".jpeg", ".png", ".bmp"}
    items = []
    for p in root.rglob("*"):
        if p.suffix.lower() in exts:
            label = infer_label(p)
            if label:
                items.append((p, label))
    return items


class NeuClsDataset(Dataset):
    def __init__(self, items, transform):
        self.items = items
        self.transform = transform
        self.class_to_idx = {c: i for i, c in enumerate(CLASSES)}

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        path, label = self.items[idx]
        img = Image.open(path).convert("RGB")
        img = self.transform(img)
        return img, self.class_to_idx[label]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log("=== FerroTwin defect classifier training started ===")
    log(f"Data root: {DATA_ROOT}")

    if not DATA_ROOT.exists():
        log(f"ABORT: DATA_ROOT does not exist: {DATA_ROOT}. Fix the path at the top of this script and rerun.")
        return

    items = find_images(DATA_ROOT)
    if not items:
        log("ABORT: found 0 images matching any known class under DATA_ROOT. "
            "Check that DATA_ROOT points at the extracted dataset, then rerun.")
        return

    counts = {c: 0 for c in CLASSES}
    for _, label in items:
        counts[label] += 1
    log(f"Class counts: {counts}")
    log(f"Total images found: {len(items)}")

    missing = [c for c, n in counts.items() if n == 0]
    if missing:
        log(f"ABORT: these classes had zero images: {missing}. "
            "The dataset folder structure doesn't match what this script expects — check DATA_ROOT before rerunning.")
        return

    if len(items) < 1000:
        log(f"WARNING: only {len(items)} images found, expected ~1800 for the full NEU-CLS set. "
            "Continuing anyway, but double check DATA_ROOT if this looks wrong.")

    random.shuffle(items)
    val_size = int(len(items) * VAL_SPLIT)
    val_items = items[:val_size]
    train_items = items[val_size:]
    log(f"Train: {len(train_items)}  Val: {len(val_items)}")

    train_tf = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(),
        transforms.RandomRotation(10),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    val_tf = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    train_loader = DataLoader(NeuClsDataset(train_items, train_tf), batch_size=BATCH_SIZE,
                               shuffle=True, num_workers=0)
    val_loader = DataLoader(NeuClsDataset(val_items, val_tf), batch_size=BATCH_SIZE,
                             shuffle=False, num_workers=0)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log(f"Using device: {device}")

    model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    model.fc = nn.Linear(model.fc.in_features, len(CLASSES))
    model = model.to(device)
    criterion = nn.CrossEntropyLoss()
    best_val_acc = 0.0

    def run_epoch(loader, train_mode, optimizer=None):
        model.train() if train_mode else model.eval()
        total_loss, correct, total = 0.0, 0, 0
        grad_ctx = torch.enable_grad() if train_mode else torch.no_grad()
        with grad_ctx:
            for imgs, labels in loader:
                imgs, labels = imgs.to(device), labels.to(device)
                if train_mode:
                    optimizer.zero_grad()
                outputs = model(imgs)
                loss = criterion(outputs, labels)
                if train_mode:
                    loss.backward()
                    optimizer.step()
                total_loss += loss.item() * imgs.size(0)
                correct += (outputs.argmax(1) == labels).sum().item()
                total += imgs.size(0)
        return total_loss / total, correct / total

    def save_if_best(val_acc, tag):
        nonlocal best_val_acc
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), OUTPUT_DIR / "best_model.pth")
            log(f"  -> new best model saved ({tag}), val_acc={val_acc:.4f}")

    # Phase 1: frozen backbone, head-only warmup
    for p in model.parameters():
        p.requires_grad = False
    for p in model.fc.parameters():
        p.requires_grad = True
    optimizer = torch.optim.Adam(model.fc.parameters(), lr=1e-3)

    log(f"--- Phase 1: head-only warmup, {HEAD_EPOCHS} epochs ---")
    for epoch in range(1, HEAD_EPOCHS + 1):
        t0 = time.time()
        train_loss, train_acc = run_epoch(train_loader, True, optimizer)
        val_loss, val_acc = run_epoch(val_loader, False)
        log(f"[head {epoch}/{HEAD_EPOCHS}] train_loss={train_loss:.4f} train_acc={train_acc:.4f} "
            f"val_loss={val_loss:.4f} val_acc={val_acc:.4f} ({time.time()-t0:.1f}s)")
        save_if_best(val_acc, f"head epoch {epoch}")

    # Phase 2: unfreeze everything, fine-tune at low LR
    for p in model.parameters():
        p.requires_grad = True
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)

    log(f"--- Phase 2: full fine-tune, {FINE_TUNE_EPOCHS} epochs ---")
    for epoch in range(1, FINE_TUNE_EPOCHS + 1):
        t0 = time.time()
        train_loss, train_acc = run_epoch(train_loader, True, optimizer)
        val_loss, val_acc = run_epoch(val_loader, False)
        log(f"[finetune {epoch}/{FINE_TUNE_EPOCHS}] train_loss={train_loss:.4f} train_acc={train_acc:.4f} "
            f"val_loss={val_loss:.4f} val_acc={val_acc:.4f} ({time.time()-t0:.1f}s)")
        save_if_best(val_acc, f"finetune epoch {epoch}")

    log(f"Training complete. Best val accuracy: {best_val_acc:.4f}")

    # Final evaluation with the BEST checkpoint (not necessarily the last epoch)
    model.load_state_dict(torch.load(OUTPUT_DIR / "best_model.pth", map_location=device))
    model.eval()
    all_preds, all_labels = [], []
    with torch.no_grad():
        for imgs, labels in val_loader:
            imgs = imgs.to(device)
            preds = model(imgs).argmax(1).cpu().numpy()
            all_preds.extend(preds)
            all_labels.extend(labels.numpy())

    cm = confusion_matrix(all_labels, all_preds)
    report = classification_report(all_labels, all_preds, target_names=CLASSES, output_dict=True)

    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(CLASSES))); ax.set_xticklabels(CLASSES, rotation=45, ha="right")
    ax.set_yticks(range(len(CLASSES))); ax.set_yticklabels(CLASSES)
    ax.set_xlabel("Predicted"); ax.set_ylabel("Actual")
    for i in range(len(CLASSES)):
        for j in range(len(CLASSES)):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                     color="white" if cm[i, j] > cm.max() / 2 else "black")
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "confusion_matrix.png", dpi=150)

    summary = {
        "finished_at": datetime.now().isoformat(),
        "device": str(device),
        "best_val_accuracy": best_val_acc,
        "class_counts": counts,
        "train_size": len(train_items),
        "val_size": len(val_items),
        "classes": CLASSES,
        "confusion_matrix": cm.tolist(),
        "classification_report": report,
    }
    with open(OUTPUT_DIR / "training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    log(f"Saved: {OUTPUT_DIR / 'best_model.pth'}")
    log(f"Saved: {OUTPUT_DIR / 'confusion_matrix.png'}")
    log(f"Saved: {OUTPUT_DIR / 'training_summary.json'}")
    log("=== Done. Safe to review in the morning. ===")


if __name__ == "__main__":
    main()
