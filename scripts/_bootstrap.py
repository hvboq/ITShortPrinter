from __future__ import annotations

import os
import sys
from pathlib import Path


def project_root() -> Path:
    """Return the repository root, respecting the operational override."""
    return Path(
        os.environ.get("MONEYPRINTER_ROOT", Path(__file__).resolve().parents[1])
    ).resolve()


def ensure_project_imports() -> None:
    """Make root and src imports work when scripts are run by filename."""
    root = project_root()
    for path in (root, root / "src"):
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)


ensure_project_imports()
