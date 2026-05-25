from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.etl_jobs import generate_process_guarde


def main() -> None:
    params = {}
    input_path = os.environ.get("PROCESS_GUARDE_INPUT_PATH", "").strip()
    output_path = os.environ.get("PROCESS_GUARDE_OUTPUT_PATH", "").strip()
    if input_path:
        params["input_path"] = input_path
    if output_path:
        params["output_path"] = output_path

    output = generate_process_guarde(params)
    print(output)


if __name__ == "__main__":
    main()