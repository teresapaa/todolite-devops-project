"""Monitoring for each toggle state.

Every event stores the flag and the variant ("on"/"off") the user was in,
so `python flagctl.py report` can compare the two groups side by side.
Recording must never break a request, so failures are only logged.
"""
import logging
from models import db, Event

log = logging.getLogger(__name__)


def record(name, flag, variant, user_id=None, value=None, once=False):
    try:
        if once and Event.query.filter_by(name=name, flag=flag, variant=variant,
                                          user_id=user_id).first():
            return
        db.session.add(Event(name=name, flag=flag, variant=variant, user_id=user_id, value=value))
        db.session.commit()
        log.info("event=%s flag=%s variant=%s user=%s value=%s", name, flag, variant, user_id, value)
    except Exception:  # noqa: BLE001 - monitoring is best effort
        db.session.rollback()
        log.exception("could not record event %s", name)
