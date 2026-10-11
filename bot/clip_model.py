"""CLIP zero-shot image scoring: how much a booking photo stands out.

Free and local: openai/clip-vit-base-patch32 (~600 MB) downloads from Hugging Face and scores the
shortlist on the Actions CPU in seconds. Needs torch, transformers and pillow (scrape workflow only).
Same approach as minneapolismugshots/bot/clip_model.py; prompts tuned for Florida.
"""
from functools import lru_cache

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

MODEL_NAME = "openai/clip-vit-base-patch32"

# Edit these to change what "stands out" means
DISTINCTIVE_PROMPTS = [
    "a mugshot of a person with face tattoos",
    "a mugshot of a person with neck or head tattoos",
    "a mugshot of a person with brightly dyed hair",
    "a mugshot of a person with a wild, unusual hairstyle",
    "a mugshot of a person making a funny or exaggerated facial expression",
    "a mugshot of a person smiling or laughing",
    "a mugshot of a person with many facial piercings",
    "a mugshot of a person with an unusual beard or facial hair",
    "a mugshot of a person wearing an unusual outfit, costume or no shirt",
    "a mugshot of a person with a black eye, cuts or a messy disheveled look",
    "a mugshot of a strikingly attractive, model-like person",
]
# Keep this list about as long as DISTINCTIVE_PROMPTS so ordinary photos don't score high by default
PLAIN_PROMPTS = [
    "a plain, ordinary mugshot of a person with a neutral expression",
    "a normal mugshot of a person with ordinary hair and no tattoos",
    "a boring, unremarkable police booking photo",
    "a mugshot of an average-looking person",
    "a mugshot of a person with short, plain hair",
    "a mugshot of a person with a tired, blank expression",
    "a mugshot of a person wearing a plain t-shirt",
    "a typical booking photo of a person against a gray wall",
    "a mugshot of a person with no visible tattoos or piercings",
    "a forgettable, everyday mugshot",
    "a mugshot of a person in a jail uniform looking at the camera",
]


@lru_cache(maxsize=1)
def _model():
    return CLIPModel.from_pretrained(MODEL_NAME).eval(), CLIPProcessor.from_pretrained(MODEL_NAME)


def _share(path, positive, negative):
    """Probability mass CLIP puts on the positive prompts, out of positive + negative."""
    model, processor = _model()
    image = Image.open(path).convert("RGB")
    inputs = processor(text=positive + negative, images=image, return_tensors="pt", padding=True)
    with torch.no_grad():
        probs = model(**inputs).logits_per_image.softmax(dim=1)[0]
    return float(probs[:len(positive)].sum())


def score_mugshots(paths):
    """Return {path: score in 0..1}, higher = more distinctive. Unreadable images score 0."""
    _model()  # A model download failure raises here, before any image is scored
    scores = {}
    for path in paths:
        try:
            scores[path] = _share(path, DISTINCTIVE_PROMPTS, PLAIN_PROMPTS)
        except Exception as e:
            print(f"⚠️  Could not score {path}: {e}")
            scores[path] = 0.0
    return scores
