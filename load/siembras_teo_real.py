from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.etl_jobs import generate_siembras_teo_real


def main() -> None:
    print(generate_siembras_teo_real())


if __name__ == "__main__":
    main()