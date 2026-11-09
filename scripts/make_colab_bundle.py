"""Pack what the Google Colab notebook needs into one zip.

    python scripts/make_colab_bundle.py

The GitHub repository is private, so Colab cannot clone it without a password.
Instead, upload this zip in the notebook's first cell (no passwords involved).

It holds the AI code (agv_brain/ without the website), the factory settings
(config/factory_layout.yaml and materials.yaml only: no device keys, no MQTT
settings), the real KIT layouts used as a test, the AI scripts, the current
trained models and the notebook itself.

Writes data/generated/carkaroo_colab.zip (not in git).
"""

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INCLUDE = [
    "agv_brain/*.py",
    "config/factory_layout.yaml",
    "config/materials.yaml",
    "data/external/kit_agv_layouts/**/*",
    "data/sample/*.csv",
    "models/*.joblib",
    "notebooks/carkaroo_ai_colab.ipynb",
    "requirements.txt",
    *[f"scripts/{name}.py" for name in (
        "generate_dataset", "train_ranker", "train_live", "evaluate", "evaluate_real_layouts",
        "generate_risk_dataset", "train_risk", "evaluate_risk", "plot_style", "demo")],
]
NEVER = (".local.yaml", ".env", ".pem", ".key")


def files() -> list[Path]:
    out = set()
    for pattern in INCLUDE:
        for p in ROOT.glob(pattern):
            if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(NEVER):
                out.add(p)
    return sorted(out)


def main() -> None:
    out = ROOT / "data" / "generated" / "carkaroo_colab.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    found = files()
    if not (ROOT / "notebooks" / "carkaroo_ai_colab.ipynb").exists():
        sys.exit("notebooks/carkaroo_ai_colab.ipynb is missing")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in found:
            z.write(p, Path("carkaroo") / p.relative_to(ROOT))
    print(f"{len(found)} files, {out.stat().st_size / 1e6:.1f} MB -> {out}")
    print("Upload this file in the first cell of the Colab notebook.")


if __name__ == "__main__":
    main()
