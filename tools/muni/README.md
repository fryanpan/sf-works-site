# tools/muni

Muni waits, crowding and Upgrade a Bus Line. `muni-ewt/` builds the wait-time and crowding figures from 511's data; `rt-archive/` is the realtime archive, kept whole because `vm-setup.sh` installs it on its own VM.

    python3 pipeline/transportation-update.py --only muni-gtfs,muni-frequency,muni-site-data,muni-optimizer
    bash tools/muni/rt-archive/vm-setup.sh                        # on the archive VM
