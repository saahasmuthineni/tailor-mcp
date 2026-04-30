# Multi-subject pilot example

Synthetic three-participant CSV data for the v6.2 multi-subject pilot
framing. Three days × hourly heart-rate + blood-glucose rows per
participant, with one deliberate "anomaly" hour each so the LLM has
something to find.

## Layout

```
examples/multi_subject_pilot/
  csv/
    P001.csv          72 rows; glucose spike on day 2 at 14:00
    P002.csv          72 rows; nighttime HR spike on day 2 at 02:00
    P003.csv          72 rows; combined HR + glucose excursion on day 3 at 12:00
  user_config.example.json    portable config — replace <REPO_ROOT>
  generate.py                 deterministic regenerator (seed = 42)
```

## Running the pilot

The full quickstart lives at
[`docs/guides/multi-subject-pilot.md`](../../docs/guides/multi-subject-pilot.md).
It walks from `git clone` through registering the server with Claude
Desktop and a first multi-subject analytical conversation in roughly
fifteen minutes.

## Regenerating the data

```bash
python examples/multi_subject_pilot/generate.py
```

Output is deterministic. Edit the `PARTICIPANTS` list near the top of
`generate.py` to add more participants or adjust baselines.
