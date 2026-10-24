"""Tests for query decomposition (v3.c item 3.5)."""

from api.analyze import split_facts, _fallback_table_for_fragments


# --- split_facts unit tests ---


def test_split_on_and():
    frags = split_facts("he stole my bike and hit me")
    assert frags == ["he stole my bike", "hit me"]


def test_split_on_comma():
    frags = split_facts("stole phone, snatched chain, hit victim")
    assert len(frags) == 3
    assert all(" " in f for f in frags)


def test_split_on_semicolon():
    frags = split_facts("took my watch; then broke my arm")
    assert frags == ["took my watch", "broke my arm"]


def test_split_on_then():
    frags = split_facts("he deceived me then ran away with cash")
    assert frags == ["he deceived me", "ran away with cash"]


def test_single_fact_unchanged():
    assert split_facts("someone stole my motorcycle") == ["someone stole my motorcycle"]


def test_empty_input():
    assert split_facts("") == []
    assert split_facts("   ") == []


def test_min_word_filter():
    # "and me" would produce a 1-word tail; must be dropped
    frags = split_facts("he hit me and shoved me")
    assert all(len(f.split()) >= 2 for f in frags)
    assert frags == ["he hit me", "shoved me"]


def test_max_fragment_cap():
    long = "a b, c d, e f, g h, i j, k l"
    frags = split_facts(long)
    assert len(frags) <= 4


def test_lead_conjunction_stripped():
    # Leading conjunction is intentionally stripped: "then shoved me" -> "shoved me"
    frags = split_facts("he hit me and then shoved me")
    assert frags == ["he hit me", "shoved me"]
    assert all(not f.lower().startswith("and ") for f in frags)


# --- fallback integration ---


def test_fallback_table_per_fragment():
    frags = ["someone stole my motorcycle", "he hit me with a stick"]
    rows = _fallback_table_for_fragments(frags)
    concepts = {r["concept"] for r in rows}
    assert "theft" in concepts
    assert "hurt" in concepts
    # each row is tagged with which fragment produced it
    assert all("fragment" in r for r in rows)
    assert all(isinstance(r["fragment"], int) for r in rows)
    assert all(r["fragment_text"] for r in rows)


def test_fallback_dedupes_by_concept():
    # Both fragments trigger theft; only one row should survive
    frags = ["he stole my phone", "he stole my motorcycle"]
    rows = _fallback_table_for_fragments(frags)
    theft_rows = [r for r in rows if r["concept"] == "theft"]
    assert len(theft_rows) == 1


def test_fallback_single_fragment_matches_old_behaviour():
    frags = ["someone stole my motorcycle"]
    rows = _fallback_table_for_fragments(frags)
    assert len(rows) >= 1
    assert rows[0]["concept"] == "theft"
    assert rows[0]["fragment"] == 0
