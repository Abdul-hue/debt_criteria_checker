"""
credit_report_extractor.py — backwards-compatibility shim.

The real implementation now lives in debt_app/integrations/credit_report.py.
This module only re-exports it, so the existing import sites

    from debt_app.credit_report_extractor import extract_credit_report
    from debt_app.credit_report_extractor import normalise_start_date_iso
    from debt_app.credit_report_extractor import extract_public_information

keep working and pick up the current implementation instead of a stale copy.

Why this exists
---------------
The package reorganisation that moves these call sites onto the new path is not
released yet. Without this shim, production keeps importing an old duplicate of
the extractor, so fixes to the real module (e.g. the missing DP/EW/EE/IL/BK
account type codes, which silently dropped creditors and their current
balances) never take effect on the running service.

DELETE THIS FILE once the reorganisation lands and every import site points at
debt_app.integrations.credit_report. It is a bridge, not an API.
"""

# Re-export the public surface. The star import keeps this shim from going stale
# if the module gains new public names; the explicit list documents what callers
# actually use today and makes a missing name fail loudly at import time rather
# than at first call.
from debt_app.integrations.credit_report import *  # noqa: F401,F403
from debt_app.integrations.credit_report import (  # noqa: F401
    CREDITOR_ALIAS_MAP,
    DEBT_TYPE_CODES,
    RECONCILIATION_ONLY_TYPE_CODES,
    SKIP_TYPE_CODES,
    extract_credit_report,
    extract_public_information,
    match_creditor,
    normalise_start_date_iso,
)
