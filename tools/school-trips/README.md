# tools/school-trips

Safer School Trips: the school-trip model (`school-sim.py`) and its inputs, the case studies, budget plans and figures, street grades, and the check against SFUSD's Travel Tally. The full model run is `school-trips-vm.sh`, on a cloud VM.

    python3 pipeline/transportation-update.py --only school-sim
    bash tools/school-trips/school-trips-vm.sh                    # the full run, on the VM
    node tools/school-trips/school-trips-figures.mjs --check
