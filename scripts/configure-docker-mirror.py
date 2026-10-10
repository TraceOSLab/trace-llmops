#!/usr/bin/env python3
"""Merge the Tencent Cloud mirror into a server's Docker daemon configuration."""

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-path", type=Path, default=Path("/etc/docker/daemon.json"))
    args = parser.parse_args()
    target = args.config_path
    template = Path(__file__).resolve().parent.parent / "docker/daemon.json.example"
    mirrors = json.loads(template.read_text())["registry-mirrors"]
    existing = json.loads(target.read_text()) if target.exists() else {}
    if not isinstance(existing, dict):
        raise ValueError("Docker daemon configuration must be a JSON object")
    current = existing.get("registry-mirrors", [])
    if not isinstance(current, list) or not all(isinstance(item, str) for item in current):
        raise ValueError("registry-mirrors must be a list of URLs")
    updated = {**existing, "registry-mirrors": list(dict.fromkeys([*mirrors, *current]))}
    if updated == existing:
        print("Docker mirror is already configured; no files changed.")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup_fd, backup_name = tempfile.mkstemp(prefix="daemon.json.backup.", dir=target.parent)
        os.close(backup_fd)
        shutil.copyfile(target, backup_name)
        print(f"Existing configuration backed up to {backup_name}")
    candidate_fd, candidate_name = tempfile.mkstemp(prefix="daemon.json.new.", dir=target.parent)
    try:
        with os.fdopen(candidate_fd, "w") as output:
            json.dump(updated, output, indent=2)
            output.write("\n")
        os.replace(candidate_name, target)
    finally:
        Path(candidate_name).unlink(missing_ok=True)
    print(f"Updated {target}; validate the configuration and restart Docker to apply it.")


if __name__ == "__main__":
    main()
