"""Download the CLIP weights at BUILD time and commit them to the image.

Run only by the Dockerfile's builder stage. The running container has
HF_HUB_OFFLINE=1 and never reaches the network; this is the one moment the
weights are fetched, and the image digest pins them afterwards.
"""
import os
import sys

from transformers import CLIPModel, CLIPProcessor

model_id = os.environ.get("CLIP_MODEL", "openai/clip-vit-base-patch32")
revision = os.environ.get("CLIP_REVISION", "main")
dest = os.environ.get("CLIP_DEST", "/models/clip")

model = CLIPModel.from_pretrained(model_id, revision=revision)
processor = CLIPProcessor.from_pretrained(model_id, revision=revision)
model.save_pretrained(dest)
processor.save_pretrained(dest)

n_params = sum(p.numel() for p in model.parameters())
print(f"baked model={model_id} revision={revision} dest={dest} params={n_params}", file=sys.stderr)
