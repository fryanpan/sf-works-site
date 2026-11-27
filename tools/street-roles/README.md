# tools/street-roles

The Street Roles Map (`/transportation/street-roles`): a role for every street block, its bike traffic stress today and with the network, and the short commutes connected at stress level 2 or better.

    python3 tools/street-roles/street-roles.py prepare --lodes <ca_od_main_JT00_2023.csv.gz>
    tools/street-roles/street-roles-vm.sh          # the route stage, on the GCP VM
    node tools/street-roles/parity.mjs             # the browser model against the build

Not on a schedule yet: the map is a snapshot of the sources its script names, and isn't registered in the refresh runner.
