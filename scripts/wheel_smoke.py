"""Build-independent fresh wheel installation, without importing the checkout."""

import os
import subprocess
import tempfile
import venv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
wheels = list((root / "dist").glob("*.whl"))
if len(wheels) != 1:
    raise SystemExit("Expected exactly one built wheel")
with tempfile.TemporaryDirectory(prefix="redirect-ledger-smoke-") as scratch:
    base = Path(scratch)
    venv.create(base / "venv", with_pip=True)
    scripts = base / "venv" / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    subprocess.run(  # noqa: S603 - only the freshly created venv interpreter is executed
        [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheels[0])],
        check=True,
        cwd=base,
        env=environment,
    )  # noqa: S603
    subprocess.run(  # noqa: S603 - fixed module and arguments, no shell
        [str(python), "-I", "-m", "redirect_ledger", "--version"],
        check=True,
        cwd=base,
        env=environment,
    )  # noqa: S603
    subprocess.run(  # noqa: S603 - fixed unittest command, no shell
        [str(python), "-I", "-m", "unittest", "discover", "-s", str(root / "tests"), "-v"],
        check=True,
        cwd=base,
        env=environment,
    )  # noqa: S603
