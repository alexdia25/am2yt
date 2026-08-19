"""Pick the right YouTube video for an Apple Music track.

Scoring blends title and artist similarity, then penalises candidates whose
runtime disagrees with the Apple track -- the cheapest reliable way to reject
remixes, snippets, and hour-long uploads that share a title.

A candidate is only auto-accepted when it is both strong on its own and clearly
ahead of the runner-up. Everything else goes to the user.
"""

from __future__ import annotations

from rapidfuzz import fuzz

from models import Candidate, Track

MIN_SCORE = 85.0
MIN_MARGIN = 15.0

TITLE_WEIGHT = 0.6
ARTIST_WEIGHT = 0.4
DURATION_TOLERANCE_S = 7
PENALTY_PER_S = 2.0
MAX_PENALTY = 40.0


def score(track: Track, candidate: Candidate) -> float:
    """Rate how well a candidate matches a track, 0..100."""
    title = fuzz.token_set_ratio(track.title, candidate.title)
    base = TITLE_WEIGHT * title + ARTIST_WEIGHT * _artist_similarity(
        track.artist, candidate.artist
    )
    return max(0.0, base - _duration_penalty(track, candidate))


def rank(track: Track, candidates: list[Candidate]) -> list[tuple[Candidate, float]]:
    """Score every candidate and return them best first."""
    scored = [(candidate, score(track, candidate)) for candidate in candidates]
    return sorted(scored, key=lambda pair: pair[1], reverse=True)


def is_confident(ranked: list[tuple[Candidate, float]]) -> bool:
    """True when the top candidate is strong and clearly ahead of the rest."""
    if not ranked:
        return False
    best = ranked[0][1]
    if best < MIN_SCORE:
        return False
    if len(ranked) == 1:
        return True
    return best - ranked[1][1] >= MIN_MARGIN


def _artist_similarity(track_artist: str, candidate_artist: str) -> float:
    """Compare artist credits, tolerating extra featured names.

    YouTube Music credits features that Apple leaves off, so "Sam Fender" has to
    match "Sam Fender, Olivia Dean". token_set_ratio alone scores that 61, low
    enough to sink a correct match below the confidence floor; partial_ratio
    scores it 100. Taking the better of the two keeps real matches confident
    without pulling wrong artists up -- a cover by "Matt Terry" still scores 38.
    """
    if not track_artist or not candidate_artist:
        return 0.0
    return max(
        fuzz.token_set_ratio(track_artist, candidate_artist),
        fuzz.partial_ratio(track_artist.lower(), candidate_artist.lower()),
    )


def _duration_penalty(track: Track, candidate: Candidate) -> float:
    if track.duration_ms is None or candidate.duration_s is None:
        return 0.0
    delta = abs(candidate.duration_s - track.duration_ms / 1000)
    if delta <= DURATION_TOLERANCE_S:
        return 0.0
    return min(MAX_PENALTY, (delta - DURATION_TOLERANCE_S) * PENALTY_PER_S)
