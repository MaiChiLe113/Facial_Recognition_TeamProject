"""MobileNetV2 live/spoof classifier (PyTorch).

Label convention everywhere in this folder: 1 = live (real face), 0 = spoof.
The network outputs ONE logit; sigmoid(logit) = P(live).

Transfer learning: ImageNet weights are loaded, the first `freeze_until` blocks of
`features` are frozen, and the remaining blocks + a new 1-unit head are fine-tuned.
This is "partial fine-tuning", which the assignment brief allows.
"""
from __future__ import annotations

import torch
import torch.nn as nn
from torchvision.models import MobileNet_V2_Weights, mobilenet_v2

IMG_SIZE = 224
MEAN = (0.485, 0.456, 0.406)  # ImageNet statistics (the backbone was pretrained with them)
STD = (0.229, 0.224, 0.225)
N_BLOCKS = 19  # mobilenet_v2().features has 19 blocks (0..18)


def build_model(pretrained: bool = True, freeze_until: int = 14, dropout: float = 0.2) -> nn.Module:
    """MobileNetV2 with a 1-logit head. Blocks [0, freeze_until) are frozen."""
    weights = MobileNet_V2_Weights.IMAGENET1K_V1 if pretrained else None
    model = mobilenet_v2(weights=weights)
    in_features = model.classifier[1].in_features  # 1280
    model.classifier = nn.Sequential(nn.Dropout(dropout), nn.Linear(in_features, 1))

    for i, block in enumerate(model.features):
        if i < freeze_until:
            for p in block.parameters():
                p.requires_grad = False
    return model


def set_train_mode(model: nn.Module, freeze_until: int) -> None:
    """model.train(), but keep frozen blocks in eval mode so their BatchNorm
    running statistics stay the ImageNet ones."""
    model.train()
    for i, block in enumerate(model.features):
        if i < freeze_until:
            block.eval()


def save_checkpoint(path, model: nn.Module, threshold: float, meta: dict) -> None:
    torch.save(
        {
            "state_dict": model.state_dict(),
            "threshold": float(threshold),
            "img_size": IMG_SIZE,
            "mean": list(MEAN),
            "std": list(STD),
            "meta": meta,
        },
        path,
    )


def load_checkpoint(path, device="cpu"):
    """Returns (model in eval mode, checkpoint dict)."""
    ckpt = torch.load(path, map_location=device, weights_only=True)
    model = build_model(pretrained=False)
    model.load_state_dict(ckpt["state_dict"])
    model.to(device).eval()
    return model, ckpt
