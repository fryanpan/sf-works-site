# tools/muni

Muni waits, crowding and Upgrade a Bus Line. `muni-ewt/` builds the wait-time and crowding figures from 511's data (on the VM, the `muni-511` step runs `vm_local.sh`, which fetches new months with `pull_all.py`, rebuilds the months that changed with `rerun_all.py` and summarises them with `post_all.sh`); `rt-archive/` is the realtime archive, kept whole because `vm-setup.sh` installs it on its own VM.

    python3 pipeline/transportation-update.py --only muni-gtfs,muni-frequency,muni-site-data,muni-optimizer
    bash tools/muni/rt-archive/vm-setup.sh                        # on the archive VM
