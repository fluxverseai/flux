"""Entry point for the flux CLI when installed as a package."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Run the flux CLI by delegating to the existing bin/flux script.

    This is a transitional entry point. Later waves will migrate the CLI
    logic into proper Python modules within this package.
    """
    bin_flux = Path(__file__).resolve().parent.parent / "bin" / "flux"
    if not bin_flux.exists():
        print(f"Error: bin/flux not found at {bin_flux}", file=sys.stderr)
        sys.exit(1)

    result = subprocess.run(  # noqa: S603, S607
        [sys.executable, str(bin_flux), *sys.argv[1:]],
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
