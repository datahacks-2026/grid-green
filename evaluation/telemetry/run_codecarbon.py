"""Run runnable workloads under CodeCarbon and write observed_emissions.csv."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "evaluation" / "configs" / "telemetry_config.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "observed_emissions.csv"


def _load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(config_path: Path, output_path: Path) -> Path:
    cfg = _load_config(config_path)
    rows: list[dict[str, str | float]] = []

    for item in cfg.get("workloads", []):
        wid = item["id"]
        path = (REPO_ROOT / item["path"]).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)

        # Patch workload main to print emissions (subprocess runs __main__).
        # Workloads call run_with_codecarbon which we wrap by executing script.
        proc = subprocess.run(
            [sys.executable, "-c", _inline_runner(path, wid)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"{wid} failed:\n{proc.stderr or proc.stdout}")
        emissions_kg = float(proc.stdout.strip().splitlines()[-1])
        rows.append({"project_name": wid, "emissions": emissions_kg})
        print(f"{wid}: {emissions_kg:.6f} kg CO2")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["project_name", "emissions"])
        writer.writeheader()
        writer.writerows(rows)

    return output_path


def _inline_runner(path: Path, project_name: str) -> str:
    return (
        "import importlib.util, pathlib, sys\n"
        f"repo = pathlib.Path({str(REPO_ROOT)!r})\n"
        "sys.path.insert(0, str(repo))\n"
        f"p = pathlib.Path({str(path)!r})\n"
        "spec = importlib.util.spec_from_file_location('wl', p)\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "from evaluation.telemetry._runner import run_with_codecarbon\n"
        f"kg = run_with_codecarbon({project_name!r}, mod._run)\n"
        "print(kg)\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture CodeCarbon emissions for telemetry workloads.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    out = run(args.config.resolve(), args.output.resolve())
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
