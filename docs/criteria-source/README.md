# Criteria workbook: source copies and update procedure

The app never reads the Excel workbook directly. It reads the markdown files in
`Excel Criteria/`, which are generated from the workbook. This folder keeps a
dated copy of every workbook version we have imported, plus the comparison
report for each update, so the next update always has a baseline.

| File | What it is |
|------|------------|
| `2026-08-21 TIP CRITERIA & VOTING HISTORY.xlsx` | The version the original markdown files were built from |
| `2026-10-12 TIP CRITERIA & VOTING HISTORY.xlsx` | Current version (received from the sheet owner, 12 Oct 2026) |
| `2026-10-12 changes since 2026-08-21.txt` | Name-matched comparison of the two, produced by `compare_excel_criteria` |

## When a new workbook arrives

1. Save it here as `YYYY-MM-DD TIP CRITERIA & VOTING HISTORY.xlsx`.
2. See what changed, matched by creditor / council name (row numbers are not reliable):

       python manage.py compare_excel_criteria --old "docs/criteria-source/<previous>.xlsx" --new "docs/criteria-source/<new>.xlsx" --out "docs/criteria-source/<date> changes since <previous date>.txt"

   Send anything odd in the report (duplicate names, remarks typed into name cells, statuses that are not one of Accept / Reject / Will Consider / Do Not Vote, swapped dates) back to the sheet owner before going further.
3. Regenerate the markdown files. Nothing is written to the database by this step.

       python manage.py export_excel_criteria --xlsx "docs/criteria-source/<new>.xlsx" --dry-run    # report only
       python manage.py export_excel_criteria --xlsx "docs/criteria-source/<new>.xlsx"              # write Excel Criteria/*.md

   Read the report. `FIX` lines are known workbook mistakes the exporter corrects (listed in `debt_app/services/excel_criteria.py`); `DROPPED` rows are deliberately left out; `KEPT` rows exist only in the previous markdown and were carried over; `RENAMED` rows changed name in the workbook. Add new fixes or renames to that module rather than editing the markdown by hand.
4. Check the three hand-maintained files against the report's criteria-sheet section: `TIG_Criteria.md`, `Watch_Criteria.md`, `TIX_Criteria.md`.
5. Review the git diff of `Excel Criteria/` and commit.
6. Apply the changes to the database, in this order, after a backup of `data/db.sqlite3`:

       python manage.py seed_creditor_criteria --dry-run        # notes-only: free text, contacts, new creditors, agreed renames
       python manage.py seed_creditor_criteria
       python manage.py seed_all_councils --dry-run             # adds new councils only; never pass --overwrite on a live database
       python manage.py seed_all_councils
       python manage.py build_criteria_change_from_excel --dry-run
       python manage.py build_criteria_change_from_excel --user <your username>
       python manage.py record_criteria_baseline --note "Before the <date> workbook update" --created-by <your username>

   `record_criteria_baseline` records the live criteria as a numbered version BEFORE anything is approved. Approvals only snapshot the state after each change, so without it a rollback would land on the last approved version and undo any hand edits made since. It records nothing if the live state already matches the latest version. The row-by-row manifest for the October 2026 update is in `2026-10-13 phase-3 apply manifest.txt` in this folder.

   The builder creates DRAFT change requests only (one per group: creditor statuses, council statuses, dividends and representatives, rule switches, HMRC equity rule). A manager trials each one on the Criteria Changes page and a second manager approves it; that is what actually changes statuses, representatives, dividends, flags and rule switches, with a numbered version and rollback. `seed_creditor_criteria` never deletes rows and, in its default mode, never writes those managed fields. Rows last edited by hand in admin are skipped unless you pass `--include-manual`. Do not use `seed_creditor_criteria --full` on a live database: it bypasses the change workflow.

## Known workbook quirks handled by the exporter

- Second "Ashford Borough Council" row is Aylesbury Vale's record with the name overwritten (dropped).
- "Copeland Borough Council" name cell carries a Cumberland remark (moved to notes).
- "Hillingdon Credit Union" and "Match the Cash" name cells carry remarks (moved to notes).
- "Clever Money" became "Clevr Money"; "Knowsley Credit Union" became "Knowsley Mutual Credit Union" (renames).
- "Startline Motor Finance" status "can get a vote if chased" is not a status (kept as DO NOT VOTE, wording in notes).
- "Partners Credit Union" updated date had day and month swapped.
- Blank county-name rows in County Councils are recognised from their districts (Kent, Norfolk).
- The Evolve representative was retired on 2026-10-12, so the EVOLVE section is not exported (`--keep-evolve` restores it).
