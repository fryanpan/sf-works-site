# tools/projects

City project records, department project pages, street work, and the coordination of projects across departments. `fixtures/` holds the gold answers `sfmta-page-dates.py` scores its date reading against.

    python3 pipeline/transportation-update.py --only sfmta-projects,project-record,street-work-list,coordination-projects,department-overlap
