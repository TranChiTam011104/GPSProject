"""Run notebooks with a real Jupyter kernel and save their outputs into the .ipynb files.

Same result as "Run All" in VS Code, but from the command line, so long notebooks can run
in the background. Each notebook runs with its own folder as the working directory
(notebooks use paths such as ``../data`` and ``outputs/``).

Usage::

    python scripts/run_notebooks.py notebooks/05_staypoint_cleaning_impact.ipynb
    python scripts/run_notebooks.py notebooks/0*.ipynb notebooks/10_*.ipynb

Prints ``----- cell i ok`` after each code cell. If a cell fails, the outputs so far (with the
traceback in the failing cell) are still saved and the script exits with code 1.
Requires ``nbclient`` (dev extra) and a ``python3`` kernel (``ipykernel``) in the environment.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError


def run(path: Path) -> bool:
    nb = nbformat.from_dict(nbformat.validator.normalize(nbformat.read(path, as_version=4))[1])  # adds missing cell ids
    code_cells = [i for i, c in enumerate(nb.cells) if c.cell_type == "code"]

    def report(cell, cell_index, execute_reply) -> None:
        print(f"----- cell {code_cells.index(cell_index)} ok", flush=True)

    client = NotebookClient(nb, timeout=None, kernel_name="python3",
                            resources={"metadata": {"path": str(path.parent)}}, on_cell_executed=report)
    ok = True
    try:
        client.execute()
    except CellExecutionError as exc:
        print(str(exc)[-3000:], flush=True)
        ok = False
    nbformat.write(nb, path)
    print(f"saved {path.name} ({path.stat().st_size / 1e3:.0f} kB){'' if ok else ' WITH ERROR'}", flush=True)
    return ok


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    if sys.platform == "win32":  # zmq needs a selector event loop on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    results = [run(Path(p).resolve()) for p in argv]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
