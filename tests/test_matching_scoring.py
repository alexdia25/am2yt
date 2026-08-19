import pytest

from matching import MIN_SCORE, is_confident, rank, score
from models import Candidate, Track

TRACK = Track(
    apple_id="1817609509",
    title="Man I Need",
    artist="Olivia Dean",
    album="The Art of Loving",
    duration_ms=184000,
)

EXACT = Candidate("fsGjRf-N71I", "Man I Need", "Olivia Dean", "The Art of Loving", 184)
REMIX = Candidate("q36OuzoFDu8", "Man I Need (Remix)", "Hiko", "Man I Need (Remix)", 71)
COVER = Candidate("YG7WEnYSpZI", "Man I Need", "Matt Terry", "Man I Need", 185)
LIVE = Candidate(
    "FUiivq_tx4s",
    "Man I Need (Australian Idol Live Performance)",
    "Kesha Oayda",
    "The Idol Collection",
    129,
)
UNRELATED = Candidate("oW_nP__Lk_U", "The Hardest Part", "Olivia Dean", "Messy", 177)


def test_exact_match_scores_at_the_top_of_the_range():
    assert score(TRACK, EXACT) >= MIN_SCORE


def test_exact_match_beats_every_trap():
    exact = score(TRACK, EXACT)
    for trap in (REMIX, COVER, LIVE, UNRELATED):
        assert exact > score(TRACK, trap)


def test_wrong_duration_is_penalised():
    close = Candidate("a", "Man I Need", "Olivia Dean", None, 184)
    far = Candidate("b", "Man I Need", "Olivia Dean", None, 71)
    assert score(TRACK, close) > score(TRACK, far)


def test_small_duration_difference_is_not_penalised():
    exact = Candidate("a", "Man I Need", "Olivia Dean", None, 184)
    within_tolerance = Candidate("b", "Man I Need", "Olivia Dean", None, 188)
    assert score(TRACK, exact) == score(TRACK, within_tolerance)


def test_missing_duration_does_not_penalise():
    unknown = Candidate("a", "Man I Need", "Olivia Dean", None, None)
    known = Candidate("b", "Man I Need", "Olivia Dean", None, 184)
    assert score(TRACK, unknown) == score(TRACK, known)


def test_artist_credited_with_extra_features_still_matches():
    """YouTube credits features Apple omits. This must not sink a real match."""
    track = Track("1", "Rein Me In", "Sam Fender", None, 340000)
    candidate = Candidate("c", "Rein Me In", "Sam Fender, Olivia Dean", None, 340)
    assert score(track, candidate) >= MIN_SCORE


def test_tolerating_extra_features_does_not_promote_a_wrong_artist():
    assert score(TRACK, COVER) < MIN_SCORE


def test_a_missing_artist_on_either_side_does_not_fake_a_match():
    no_artist_track = Track("1", "Man I Need", "", None, 184000)
    assert score(no_artist_track, EXACT) < MIN_SCORE
    assert score(TRACK, Candidate("a", "Man I Need", "", None, 184)) < MIN_SCORE


def test_score_is_bounded():
    for candidate in (EXACT, REMIX, COVER, LIVE, UNRELATED):
        assert 0.0 <= score(TRACK, candidate) <= 100.0


def test_rank_orders_best_first():
    ranked = rank(TRACK, [COVER, EXACT, REMIX])
    assert [candidate.video_id for candidate, _ in ranked][0] == EXACT.video_id
    scores = [value for _, value in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_of_nothing_is_empty():
    assert rank(TRACK, []) == []


def test_clear_winner_is_confident():
    assert is_confident(rank(TRACK, [EXACT, REMIX, COVER, LIVE]))


def test_single_strong_candidate_is_confident():
    assert is_confident(rank(TRACK, [EXACT]))


def test_two_near_identical_uploads_are_not_confident():
    duplicate = Candidate("dup", "Man I Need", "Olivia Dean", "The Art of Loving", 184)
    assert not is_confident(rank(TRACK, [EXACT, duplicate]))


def test_weak_best_candidate_is_not_confident():
    assert not is_confident(rank(TRACK, [UNRELATED]))


def test_nothing_is_not_confident():
    assert not is_confident([])
