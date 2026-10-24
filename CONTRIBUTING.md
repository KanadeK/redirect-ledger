# Contributing

Start with an issue describing the input, expected result, and a minimal synthetic reproduction. Never attach private input data. Keep changes within the documented format contract.

```sh
python -m venv .venv
# Activate .venv using your shell's standard command.
python -m pip install -r requirements-dev.txt
python -m pip install -e . --no-build-isolation
python -m ruff check .
python -m ruff format --check .
python -m coverage run -m unittest discover -s tests -v
python -m coverage report
python -m build
```

Tests must cover observable behavior, invalid input, and independent reference calculations where relevant. CI has read-only repository permissions and never commits generated files. This repository does not automatically merge contributions or enable automated dependency-update commits. Changes require maintainer review; preserve third-party copyrights and licenses.

Use English for code and primary documentation. Chinese explanations are welcome in README.zh-CN.md. The runtime requires only Python 3.11+.
