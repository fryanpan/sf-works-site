# data/bos-meetings

Every Board of Supervisors and committee meeting since 2019, as read from each meeting's agenda grid on [sfgov.legistar.com](https://sfgov.legistar.com/Calendar.aspx): the files heard, their full titles, types, the action taken and its result, and each file's LegislationDetail link.

- `index.json` is tracked. It lists every meeting Legistar shows for "BOS and Committees" from 2019 on, and for each one whether it was mirrored or why not.
- `meetings/` is not tracked. It is about 30 MB, so it is gitignored and rebuilt from Legistar:

```
bash pipeline/site-refresh/vm-setup.sh # once on the VM; it installs the scraper's virtualenv under ~/.cache/sf-legistar
tools/meetings/fetch-bos-meetings.py        # since 2019-01-01; about 1,700 meetings, one request each
tools/meetings/fetch-bos-meetings.py --since 2023-01-01 --until 2024   # a slice, to run several in parallel
```

A rerun skips every meeting already mirrored as final (held more than 45 days ago, or with minutes posted) and re-reads the rest. Individual email addresses are scrubbed at write time by `lib/mirror.py`.
