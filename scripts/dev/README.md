# Dev / verification scripts

One-off scripts used to eyeball live data or exercise a code path by hand.
They are **not** tests — the test suite lives in `debt_app/tests/`.

Run them from the repository root with the project venv:

```
python scripts/dev/verify_milestone.py
```

Several of them send real email or write to the live database. Read the script
before running it.
