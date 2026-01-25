
from agent.providers.formatters.xml_matcher import XmlMatcher


def test_only_match_at_position_0():
    matcher = XmlMatcher("think")
    chunks = [*matcher.update("<think>data</think>"), *matcher.final()]
    assert len(chunks) == 1
    assert chunks == [
        {
            "matched": True,
            "data": "data",
        }
    ]

def test_tag_with_space():
    matcher = XmlMatcher("think")
    chunks = [*matcher.update("< think >data</ think >"), *matcher.final()]
    assert len(chunks) == 1
    assert chunks == [
        {
            "matched": True,
            "data": "data",
        }
    ]

def test_invalid_tag():
    matcher = XmlMatcher("think")
    chunks = [*matcher.update("< think 1>data</ think >"), *matcher.final()]
    assert len(chunks) == 1
    assert chunks == [
        {
            "matched": False,
            "data": "< think 1>data</ think >",
        }
    ]

def test_anonymous_tag():
    matcher = XmlMatcher("think")
    chunks = [*matcher.update("<>data</>"), *matcher.final()]
    assert len(chunks) == 1
    assert chunks == [
        {
            "matched": False,
            "data": "<>data</>",
        }
    ]

def test_streaming_push():
    matcher = XmlMatcher("think")
    chunks = [
        *matcher.update("<thi"),
        *matcher.update("nk"),
        *matcher.update(">dat"),
        *matcher.update("a</"),
        *matcher.update("think>"),
    ]
    assert len(chunks) == 2
    assert chunks == [
        {
            "matched": True,
            "data": "dat",
        },
        {
            "matched": True,
            "data": "a",
        },
    ]

def test_nested_tag():
    matcher = XmlMatcher("think")
    chunks = [
        *matcher.update("<think>X<think>Y</think>Z</think>"),
        *matcher.final(),
    ]
    assert len(chunks) == 1
    assert chunks == [
        {
            "matched": True,
            "data": "X<think>Y</think>Z",
        }
    ]

def test_nested_invalid_tag():
    matcher = XmlMatcher("think")
    chunks = [
        *matcher.update("<think>X<think>Y</thxink>Z</think>"),
        *matcher.final(),
    ]
    assert len(chunks) == 2
    assert chunks == [
        {
            "matched": True,
            "data": "X<think>Y</thxink>Z",
        },
        {
            "matched": True,
            "data": "</think>",
        },
    ]

def test_wrong_matching_position():
    matcher = XmlMatcher("think")
    chunks = [*matcher.update("1<think>data</think>"), *matcher.final()]
    assert len(chunks) == 1
    assert chunks == [
        {
            "matched": False,
            "data": "1<think>data</think>",
        }
    ]

def test_unclosed_tag():
    matcher = XmlMatcher("think")
    chunks = [*matcher.update("<think>data"), *matcher.final()]
    assert len(chunks) == 1
    assert chunks == [
        {
            "matched": True,
            "data": "data",
        }
    ]