"""
criteria_engine.py — backwards-compatibility shim.

The real implementation now lives in debt_app/engine/criteria.py. This module
forwards every attribute lookup to it, so existing import sites such as

    from debt_app.criteria_engine import assess_case, detect_representatives
    from debt_app.criteria_engine import _tig_17, _match_council_rule

keep working and resolve to the current implementation instead of a stale copy.

Why this exists
---------------
The package reorganisation that moves these call sites onto the new path is not
released yet. Without this shim, production keeps importing an old duplicate of
the engine, so changes to the real module never take effect on the running
service — the majority-threshold fix (abstaining creditors excluded from the
75% base) and the MAJORITY-IMPOSSIBLE downgrade from hard block to referral
flag would both be invisible in production.

Why __getattr__ rather than `import *`
--------------------------------------
Call sites import private names (_tig_08, _tig_10, _tig_16, _tig_17, _tig_21_5,
_watch_22_7, _match_council_rule, _apply_representative_outcomes,
_check_creditor_individual, _compute_dividend_analysis, _sanitize_dmp_checklist,
_cross_check_property_from_credit_report, ...). A star import skips
underscore-prefixed names, so it would silently miss most of them. PEP 562
module __getattr__ forwards ANY name, public or private, and needs no list to
keep in sync. Nothing in the codebase does `import *` from this module, which is
the one pattern __getattr__ would not serve.

DELETE THIS FILE once the reorganisation lands and every import site points at
debt_app.engine.criteria. It is a bridge, not an API.
"""

from debt_app.engine import criteria as _real


def __getattr__(name):
    """Forward any attribute access to the real engine module."""
    try:
        return getattr(_real, name)
    except AttributeError:
        # Raise from this module's name so tracebacks point at the shim rather
        # than looking like the real module is missing something.
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r} "
            f"(forwarded to {_real.__name__!r})"
        ) from None


def __dir__():
    return sorted(set(globals()) | set(dir(_real)))
