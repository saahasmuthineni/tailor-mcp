# Multi-subject pilot example

Synthetic three-participant CSV data for the v6.2 multi-subject pilot
framing. Three days × hourly heart-rate + blood-glucose rows per
participant, with one deliberate "anomaly" hour each so the LLM has
something to find.

## Recommended path: `tailor pilot`

For most users the right command is:

```bash
tailor pilot
```

The wizard offers the bundled synthetic CSVs as the default directory,
auto-detects the schema, writes `user_config.json`, and registers the
server with Claude Desktop in one go. The full guide is at
[`docs/guides/multi-subject-pilot.md`](../../docs/guides/multi-subject-pilot.md).

## Where the synthetic CSVs actually live

Canonical home: [`src/tailor/_fixtures/multi_subject_pilot/csv/`](../../src/tailor/_fixtures/multi_subject_pilot/csv/).

They live inside the package so they ship in the wheel — that means
`uv tool install` and `pip install` users get them automatically, with
no source tree on disk.

| File | Anomaly |
|---|---|
| `P001.csv` | 72 rows; glucose spike on day 2 at 14:00 |
| `P002.csv` | 72 rows; nighttime HR spike on day 2 at 02:00 |
| `P003.csv` | 72 rows; combined HR + glucose excursion on day 3 at 12:00 |

## Manual config fallback

If you'd rather skip the wizard and edit `user_config.json` by hand, see
[`user_config.example.json`](user_config.example.json) — replace
`<REPO_ROOT>` with the absolute path to your clone.

## Regenerating the data

```bash
python examples/multi_subject_pilot/generate.py
```

Output is deterministic (seed = 42) and writes back into the package
fixtures directory. Edit the `PARTICIPANTS` list near the top of
`generate.py` to add more participants or adjust baselines.
