"""
Context-local database routing for criteria trials.

Inactive by default: every router method returns None, so Django's normal
routing (the 'default' database) applies to all ordinary requests. Only code
running inside `route_to(alias)` — the criteria trial, on its own thread/
context — is sent to the isolated trial copy. A ContextVar is used so
concurrent requests on other threads are never affected.
"""

import contextlib
import contextvars

_active_alias = contextvars.ContextVar("criteria_trial_db_alias", default=None)


@contextlib.contextmanager
def route_to(alias):
    token = _active_alias.set(alias)
    try:
        yield
    finally:
        _active_alias.reset(token)


class CriteriaTrialRouter:
    def db_for_read(self, model, **hints):
        return _active_alias.get()

    def db_for_write(self, model, **hints):
        return _active_alias.get()

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return None
