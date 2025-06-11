#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

# List of source paths to lint
SOURCE_PATHS = [
    "a_la_carte",
    "sous_chef_kitchen",
    "recipes",
    "buffet.py",
]

def run_command(command, description):
    print(f"\n=== Running {description} ===")
    result = subprocess.run(command, shell=True)
    if result.returncode != 0:
        print(f"❌ {description} failed!")
        return False
    print(f"✅ {description} passed!")
    return True

def main():
    # Get the project root directory
    project_root = Path(__file__).parent.absolute()
    # Build the source path string
    sources = " ".join(str(project_root / p) for p in SOURCE_PATHS)
    # Run isort
    isort_ok = run_command(
        f"isort {sources}",
        "isort (import sorting)"
    )
    # Run black
    black_ok = run_command(
        f"black {sources}",
        "black (code formatting)"
    )
    # Run flake8
    flake8_ok = run_command(
        f"flake8 {sources}",
        "flake8 (code linting)"
    )
    # Exit with appropriate status
    if all([isort_ok, black_ok, flake8_ok]):
        print("\n✨ All linters passed!")
        sys.exit(0)
    else:
        print("\n❌ Some linters failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
