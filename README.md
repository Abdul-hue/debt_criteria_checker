# Debt Criteria Check

Django + DRF service that decides whether a debt case meets IVA criteria, plus a
React front end. It reads case data from Aryza, evaluates it against creditor,
council and global criteria rules, and returns a decision with the rules that
fired.

## Running it

```bash
python -m venv .venv
.venv/Scripts/activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then fill in the values
python manage.py migrate
python manage.py collectstatic --noinput   # populates staticfiles/
python manage.py runserver
```

Front end:

```bash
cd frontend
npm install
npm run dev                     # or: npm run build, which Django then serves
```

Docker builds the front end and runs `collectstatic` for you:

```bash
docker compose up --build
```

## Tests

Both runners see the same suite (`debt_app/tests/`):

```bash
python manage.py test debt_app
pytest                          # config in pytest.ini
```

## Layout

```
debt_project/          Django project: settings, root URLconf, WSGI
debt_app/
  models.py            All ORM models
  admin.py             Django admin registrations
  permissions.py       Department feature/read/write DRF permissions
  engine/              Pure decision logic - no HTTP, no request objects
    criteria.py          assess_case() and the rule evaluators
    recommendation.py    Outcome -> recommendation mapping
    sfs.py               SFS expenditure arithmetic
  integrations/        Clients for systems outside this service
    aryza.py             Aryza CRM / Advize case fetch
    credit_report.py     Credit report PDF extraction
  helpers/             Shared utilities, split by concern
    creditor_names.py    Name normalisation, alias + fuzzy lookup
    creditor_aliases.py  Raw alias table (data only)
    debt_types.py        Debt-type constants and totals
    decisions.py         CriteriaDecision reads/writes
    departments.py       Department scoping of querysets
    dates.py             Europe/London day boundaries
  views/               HTTP layer
    criteria/            The /api/v1/criteria/ surface, one module per domain
    assess_direct.py     POST /api/v1/assess/
    assess_simple.py     POST /api/assess/
    evaluate.py          Case evaluation
    evaluation_history.py
    internal_sfs.py      Token-free service-to-service SFS endpoints
    departments.py       Department administration
    auth.py              Email-based JWT obtain
  serializers/         DRF serializers, by domain
  services/            Background/long-running work (CRM vote sync, digests)
  seeds/               Reference datasets used by migrations and seed commands
  management/commands/ Seed, audit and sync commands
  migrations/
  fixtures/
  tests/               Test suite (test_*.py)
frontend/              React + Vite SPA
scripts/               Scheduled-job wrappers; scripts/dev/ holds ad-hoc scripts
docs/                  Architecture notes, implementation plans, criteria reference
data/                  SQLite database (git-ignored)
logs/                  Runtime logs (git-ignored)
```

Two rules keep the layers apart:

- `engine/` never imports from `views/`. Views call the engine, not the reverse.
- `views/criteria/_shared.py` holds only helpers used by two or more sibling
  modules; single-use helpers stay with their caller.

`debt_app/helpers/__init__.py` and `debt_app/views/criteria/__init__.py`
re-export their submodules' public names, so `from debt_app.helpers import X`
keeps working. `mock.patch` targets must still name the owning module — e.g.
`debt_app.views.criteria.assess.fetch_case_by_reference`.

## Docs

| Document | What it covers |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the assessment pipeline fits together |
| [docs/EXCEL_CRITERIA_REFERENCE.md](docs/EXCEL_CRITERIA_REFERENCE.md) | Rule-by-rule reference |
| [docs/criteria/](docs/criteria/) | The source criteria spreadsheets, as markdown |
| [docs/PERMISSION_LEVELS.md](docs/PERMISSION_LEVELS.md) | Department feature permissions |
| [docs/DEBT_APP_MODELS.md](docs/DEBT_APP_MODELS.md) | Criteria model fields and audit trail |
| [docs/CA_TOOL_DEPENDENCIES.md](docs/CA_TOOL_DEPENDENCIES.md) | What the case-assessment service depends on here |
