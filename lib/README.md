# lib

Python modules the scripts import by name, plus a few small tools. Most are imported from two or more folders (`paths`, `stable`, `sfdata`, `pipeline_state`, `walknet`, `extract`, `fetch`, `quality` and others). About a dozen have one user today, such as `granicus.py`, used only by `tools/meetings/`, and `full_map_dests.py`, only by `tools/travel/`; they came over with the shared modules.

- `paths.py` finds the repo root and any script by file name. Every script starts with three lines that import it (its docstring shows them).
- `settings.py` reads the optional settings that name private infrastructure, from the environment or the gitignored `local-settings.json`.
- `trace_io/` is put on `PYTHONPATH` by `pipeline/transportation-update.py` to record the files each build step reads and writes.
- `rcsp.c` is the C core of `rcsp.py`, compiled with the system C compiler on first use.
- `school-travel-time.py` is also a refresh step, and a few modules have a command line of their own (`tree_same.py`, for one), which their docstrings show.

```
python3 -c "import sys; sys.path.insert(0, '.'); from lib import paths; print(paths.script('school-sim.py'))"
```
