from __future__ import annotations

import argparse
import logging
from pathlib import Path

from carmaker_recorder.app import run
from carmaker_recorder.config import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CarMaker CameraRSI Recorder CLI")
    parser.add_argument("--config", default="config.json", help="JSON config path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_dir = Path(__file__).resolve().parent
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = project_dir / config_path
    config = load_config(config_path)
    logging.basicConfig(
        level=getattr(logging, config.logging.level.upper()),
        format="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    run(config, project_dir)


if __name__ == "__main__":
    main()
