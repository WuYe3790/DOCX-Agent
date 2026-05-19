import json
from pathlib import Path


def load_style_sample(style_profile_path: str, sample_id: str) -> dict:
    profile = json.loads(Path(style_profile_path).read_text(encoding="utf-8"))
    for sample in profile.get("style_samples", []):
        if sample.get("sample_id") == sample_id:
            return sample
    raise ValueError(f"sample_id not found in style profile: {sample_id}")
