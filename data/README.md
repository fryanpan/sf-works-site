# data

Source data the scripts fetched or were given, one folder per source or tool. Most of it is refreshed by the steps in `pipeline/`; each folder's script names its source in its docstring, and some folders carry their own README. Files of 1 MB or more are in Git LFS.

    python3 pipeline/transportation-update.py --dry-run    # which steps would refresh what
