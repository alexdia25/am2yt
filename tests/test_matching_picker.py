import pytest

from matching import default_query, resolve
from models import Candidate, Track

TRACK = Track("1817609509", "Man I Need", "Olivia Dean", "The Art of Loving", 184000)

EXACT = Candidate("fsGjRf-N71I", "Man I Need", "Olivia Dean", "The Art of Loving", 184)
REMIX = Candidate("q36OuzoFDu8", "Man I Need (Remix)", "Hiko", "Man I Need (Remix)", 71)
COVER = Candidate("YG7WEnYSpZI", "Man I Need", "Matt Terry", "Man I Need", 185)
DUPLICATE = Candidate("dup", "Man I Need", "Olivia Dean", "The Art of Loving", 184)


def searcher(*batches):
    """A fake search that returns each batch in turn, recording its queries."""
    queries = []
    results = list(batches)

    def search(query):
        queries.append(query)
        return results.pop(0) if results else []

    search.queries = queries
    return search


def asker(*answers):
    """A fake input() that replays answers and records how many were used."""
    remaining = list(answers)

    def ask(prompt=""):
        if not remaining:
            raise AssertionError("picker asked more questions than expected")
        return remaining.pop(0)

    return ask


def test_default_query_is_title_then_artist():
    assert default_query(TRACK) == "Man I Need Olivia Dean"


def test_default_query_omits_a_missing_artist():
    assert default_query(Track("1", "Man I Need", "")) == "Man I Need"


def test_clear_winner_is_taken_without_asking():
    decision = resolve(TRACK, searcher([EXACT, REMIX, COVER]), ask=asker(), show=lambda *_: None)
    assert decision.candidate == EXACT
    assert decision.confident is True
    assert decision.stop is False


def test_no_results_at_all_is_a_skip_without_asking():
    decision = resolve(TRACK, searcher([]), ask=asker(), show=lambda *_: None)
    assert decision.candidate is None
    assert decision.confident is False
    assert decision.stop is False


def test_ambiguous_match_asks_and_honours_the_choice():
    decision = resolve(
        TRACK, searcher([EXACT, DUPLICATE]), ask=asker("2"), show=lambda *_: None
    )
    assert decision.candidate == DUPLICATE
    assert decision.confident is False


def test_choice_of_one_picks_the_top_candidate():
    decision = resolve(
        TRACK, searcher([EXACT, DUPLICATE]), ask=asker("1"), show=lambda *_: None
    )
    assert decision.candidate == EXACT


def test_s_skips_the_track():
    decision = resolve(
        TRACK, searcher([EXACT, DUPLICATE]), ask=asker("s"), show=lambda *_: None
    )
    assert decision.candidate is None
    assert decision.stop is False


def test_q_stops_the_run():
    decision = resolve(
        TRACK, searcher([EXACT, DUPLICATE]), ask=asker("q"), show=lambda *_: None
    )
    assert decision.candidate is None
    assert decision.stop is True


def test_m_searches_again_with_the_typed_query():
    search = searcher([EXACT, DUPLICATE], [COVER])
    decision = resolve(
        TRACK, search, ask=asker("m", "man i need matt terry", "1"), show=lambda *_: None
    )
    assert decision.candidate == COVER
    assert search.queries == ["Man I Need Olivia Dean", "man i need matt terry"]


def test_manual_search_never_auto_accepts():
    """The user asked to choose, so a strong result still gets confirmed."""
    search = searcher([EXACT, DUPLICATE], [EXACT])
    decision = resolve(TRACK, search, ask=asker("m", "olivia dean", "1"), show=lambda *_: None)
    assert decision.candidate == EXACT
    assert decision.confident is False


def test_manual_search_with_no_results_can_still_be_skipped():
    search = searcher([EXACT, DUPLICATE], [])
    decision = resolve(TRACK, search, ask=asker("m", "nonsense", "s"), show=lambda *_: None)
    assert decision.candidate is None


def test_a_bad_manual_search_can_be_retried():
    """Nothing found must not force a skip -- the user gets another go."""
    search = searcher([EXACT, DUPLICATE], [], [COVER])
    decision = resolve(
        TRACK,
        search,
        ask=asker("m", "nonsense", "m", "man i need matt terry", "1"),
        show=lambda *_: None,
    )
    assert decision.candidate == COVER
    assert search.queries[1:] == ["nonsense", "man i need matt terry"]


def test_quitting_works_after_a_manual_search_found_nothing():
    search = searcher([EXACT, DUPLICATE], [])
    decision = resolve(
        TRACK, search, ask=asker("m", "nonsense", "q"), show=lambda *_: None
    )
    assert decision.stop is True


def test_an_empty_manual_query_keeps_the_original_candidates():
    search = searcher([EXACT, DUPLICATE])
    decision = resolve(
        TRACK, search, ask=asker("m", "", "1"), show=lambda *_: None
    )
    assert decision.candidate == EXACT
    assert search.queries == ["Man I Need Olivia Dean"]


def test_a_number_is_not_accepted_when_there_is_nothing_to_pick():
    search = searcher([EXACT, DUPLICATE], [])
    decision = resolve(
        TRACK, search, ask=asker("m", "nonsense", "1", "s"), show=lambda *_: None
    )
    assert decision.candidate is None


def test_out_of_range_number_reprompts():
    shown = []
    decision = resolve(
        TRACK,
        searcher([EXACT, DUPLICATE]),
        ask=asker("9", "1"),
        show=shown.append,
    )
    assert decision.candidate == EXACT
    assert any("1" in str(line) and "2" in str(line) for line in shown)


def test_unrecognised_input_reprompts():
    decision = resolve(
        TRACK, searcher([EXACT, DUPLICATE]), ask=asker("wat", "s"), show=lambda *_: None
    )
    assert decision.candidate is None


def test_blank_input_reprompts():
    decision = resolve(
        TRACK, searcher([EXACT, DUPLICATE]), ask=asker("", "s"), show=lambda *_: None
    )
    assert decision.candidate is None


def test_picker_shows_the_track_and_every_candidate():
    shown = []
    resolve(TRACK, searcher([EXACT, DUPLICATE]), ask=asker("1"), show=shown.append)
    text = "\n".join(str(line) for line in shown)
    assert "Man I Need" in text
    assert "Olivia Dean" in text
    assert "3:04" in text


def test_at_most_five_candidates_are_offered():
    many = [Candidate(f"v{i}", "Man I Need", "Whoever", None, 184) for i in range(9)]
    shown = []
    resolve(TRACK, searcher(many), ask=asker("1"), show=shown.append)
    text = "\n".join(str(line) for line in shown)
    assert " 5." in text or "5." in text
    assert "6." not in text
