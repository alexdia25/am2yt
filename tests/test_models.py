import pytest

from models import Candidate, Result, Track, format_duration_ms, format_duration_s


def test_formats_seconds_as_minutes_and_seconds():
    assert format_duration_s(184) == "3:04"


def test_pads_single_digit_seconds():
    assert format_duration_s(61) == "1:01"


def test_formats_under_a_minute():
    assert format_duration_s(45) == "0:45"


def test_formats_over_an_hour_without_an_hours_field():
    assert format_duration_s(3700) == "61:40"


def test_unknown_seconds_render_as_question_marks():
    assert format_duration_s(None) == "?:??"


def test_formats_milliseconds():
    assert format_duration_ms(184000) == "3:04"


def test_rounds_milliseconds_to_the_nearest_second():
    assert format_duration_ms(184600) == "3:05"


def test_unknown_milliseconds_render_as_question_marks():
    assert format_duration_ms(None) == "?:??"


def test_a_result_with_a_candidate_is_matched():
    track = Track("1", "T", "A")
    assert Result(track, Candidate("v", "T", "A"), True).matched is True


def test_a_result_without_a_candidate_is_not_matched():
    assert Result(Track("1", "T", "A"), None, False).matched is False
