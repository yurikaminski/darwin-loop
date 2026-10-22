import re
from pathlib import Path

import queries

SQL = (Path(__file__).parent / "views.sql").read_text()


def _expr(alias):
    """Text of the SQL expression ending in `AS <alias>` (from the previous top-level comma)."""
    m = re.search(r",\s*((?:(?!,\n).)*?)\s+AS " + alias + r"\b", SQL, re.S)
    assert m, alias
    return m.group(1)


def test_behavioural_flags_ignore_text():
    # PM must_fix: managers must see the same friction with or without prompt-text opt-in.
    for alias in ("flag_fast_reprompt", "flag_abandoned", "flag_user_reject", "flag_tool_fail", "is_friction_b"):
        assert "correction" not in _expr(alias), alias
    assert "next_correction_kw" in _expr("is_friction")


def test_queries_format():
    for name, q in queries.QUERIES.items():
        sql = q.format(ds="`p.d`")
        assert "{" not in sql and "`p.d`" in sql, name
