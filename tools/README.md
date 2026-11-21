# tools

One folder per tool on the site. Each script writes the files of the tool whose folder it sits in; the refresh runner in `pipeline/` calls the ones that run on a schedule, by step name. Each folder's README lists its steps.

    python3 pipeline/transportation-update.py --only <step>
