from __future__ import annotations

import argparse
import subprocess
from pathlib import PurePosixPath


EXACT_FILES = {
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    ".github/workflows/ci.yml",
    ".githooks/pre-commit",
    "LICENSE",
    "README.md",
    "README_CN.md",
    "VERSION",
    "config.json",
    "docs/ARCHITECTURE.md",
    "docs/CONFIG_REFERENCE.md",
    "docs/VALIDATION.md",
    "examples/config_remote_multi_camera.json",
    "images/Example of Six-Channel CameraRSI Demo Map.jpg",
    "images/Example of Six-Channel CameraRSI.jpg",
    "pyproject.toml",
    "requirements-build.txt",
    "requirements-core.txt",
    "requirements-tested-core.txt",
    "requirements.txt",
    "run.py",
    "run_gui.py",
    "scripts/check_repository.py",
    "scripts/linux/prepare_offline.sh",
    "scripts/linux/start_cli.sh",
    "scripts/linux/start_gui.sh",
    "scripts/windows/build.bat",
    "scripts/windows/build.ps1",
    "scripts/windows/prepare_offline.bat",
    "scripts/windows/prepare_offline.ps1",
    "scripts/windows/start_cli.bat",
    "scripts/windows/start_cli.ps1",
    "scripts/windows/start_gui.bat",
    "scripts/windows/start_gui.ps1",
    "verify_project.py",
}
PYTHON_DIRECTORIES = {"carmaker_gui", "carmaker_recorder", "tests"}


def is_allowed(path: str) -> bool:
    normalized = PurePosixPath(path).as_posix()
    if normalized in EXACT_FILES:
        return True
    parts = PurePosixPath(normalized).parts
    return len(parts) == 2 and parts[0] in PYTHON_DIRECTORIES and normalized.endswith(".py")


def repository_files(staged: bool) -> list[str]:
    command = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"] if staged else ["git", "ls-files"]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the repository file allowlist.")
    parser.add_argument("--staged", action="store_true", help="Check only files staged for commit.")
    args = parser.parse_args()

    rejected = sorted(path for path in repository_files(args.staged) if not is_allowed(path))
    if rejected:
        print("Repository scope check failed. Remove these files from version control:")
        for path in rejected:
            print(f"  - {path}")
        return 1

    print("Repository scope check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
