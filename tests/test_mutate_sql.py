from tools.mutate_sql import code_spans, mutants_of

SQL = """
SELECT a, 'x < y AND z' AS lit, "col=1" AS q, list_transform(v, x -> x + 1)
FROM t -- WHERE a < 0 in a comment
WHERE a > 0 AND (b <= 1 OR c = 2)
GROUP BY a
HAVING min(b) <> 3
"""


def descriptions(sql):
    return [m.description for m in mutants_of("SQL", sql)]


def test_literals_identifiers_comments_and_lambdas_are_never_mutated():
    for m in mutants_of("SQL", SQL):
        assert "'x < y AND z'" in m.sql
        assert '"col=1"' in m.sql
        assert "-- WHERE a < 0 in a comment" in m.sql
        assert "x ->" in m.sql
    spans = code_spans(SQL)
    assert all("'" not in SQL[a:b] and '"' not in SQL[a:b] for a, b in spans)


def test_token_mutations():
    d = descriptions(SQL)
    for expected in [
        "comparison: `>` → `>=`",
        "comparison: `<=` → `<`",
        "comparison: `=` → `<>`",
        "comparison: `<>` → `=`",
        "logic: `AND` → `OR`",
        "logic: `OR` → `AND`",
        "min/max: `min` → `max`",
        "drop ±1: `+ 1` → `∅`",
    ]:
        assert expected in d, expected


def test_where_and_having_conditions_are_dropped_whole_and_per_conjunct():
    by_desc = {m.description: m for m in mutants_of("SQL", SQL)}
    whole = [m for d, m in by_desc.items() if d.startswith("drop WHERE:")]
    assert len(whole) == 1
    assert "WHERE TRUE\nGROUP BY a" in whole[0].sql

    conjuncts = [
        m for m in mutants_of("SQL", SQL) if m.description.startswith("drop WHERE conjunct")
    ]
    assert len(conjuncts) == 2
    assert any("WHERE TRUE AND (b <= 1 OR c = 2)" in m.sql for m in conjuncts)
    assert any("a > 0 AND TRUE" in m.sql for m in conjuncts)

    assert any(
        m.description.startswith("drop HAVING") and "HAVING TRUE" in m.sql for m in by_desc.values()
    )


def test_line_numbers_point_into_the_sql():
    [m] = [m for m in mutants_of("SQL", SQL) if m.description == "comparison: `<>` → `=`"]
    assert m.line == 6  # SQL starts with a newline: HAVING is line 6
