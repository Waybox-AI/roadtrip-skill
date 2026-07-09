"""
Tests for surviving malformed model JSON:
  * routes._escape_inner_quotes / extract_json layer 6 — unescaped quotes
    inside string values (the staging JSONDecodeError incident shape).
  * planner._parse_with_retry — one automatic second chance, with evidence
    logged to stderr.

Everything runs offline; no model calls.
"""

import json

import pytest

from scripts import planner
from scripts.routes import extract_json, _escape_inner_quotes


class TestEscapeInnerQuotes:
    def test_valid_json_passes_through_unchanged(self):
        s = json.dumps({"a": 'he said \\"hi\\"', "b": [1, 2], "c": {"d": "x"}})
        assert _escape_inner_quotes(s) == s

    def test_embedded_quote_before_letter_is_escaped(self):
        s = '{"note": "leaving "Golden Gate" at dawn"}'
        assert json.loads(_escape_inner_quotes(s)) == {
            "note": 'leaving "Golden Gate" at dawn'}

    def test_chinese_mixed_content(self):
        # the staging incident shape: zh prose quoting an English place name
        s = '{"title": "从 "Golden Gate" 出发沿一号公路", "driveMiles": 90}'
        got = json.loads(_escape_inner_quotes(s))
        assert got["title"] == '从 "Golden Gate" 出发沿一号公路'
        assert got["driveMiles"] == 90

    def test_multiple_embedded_quotes_one_string(self):
        s = '{"a": ""x" then "y" done"}'
        assert json.loads(_escape_inner_quotes(s)) == {"a": '"x" then "y" done'}

    def test_already_escaped_quotes_untouched(self):
        s = '{"a": "he said \\"hi\\" loudly"}'
        assert _escape_inner_quotes(s) == s


class TestExtractJsonLayer6:
    def test_inner_quote_document_parses(self):
        doc = ('{"title": "湾区之行", "days": [{"date": "07/11", '
               '"note": "从 "Golden Gate" 出发", "driveMiles": 90}]}')
        got = extract_json(doc)
        assert got["days"][0]["note"] == '从 "Golden Gate" 出发'

    def test_inner_quote_plus_trailing_comma(self):
        doc = '{"a": "see "X"", "b": [1, 2,],}'
        assert extract_json(doc) == {"a": 'see "X"', "b": [1, 2]}

    def test_inner_quote_plus_truncation(self):
        # both diseases at once: embedded quote early, document cut off later
        doc = ('{"a": "see "X" now", "days": [{"i": 1}, {"i": 2}, {"i": 3'
               )  # truncated mid-value
        got = extract_json(doc)
        assert got["a"] == 'see "X" now'
        assert got["days"][:2] == [{"i": 1}, {"i": 2}]

    def test_regressions_still_pass(self):
        # fences / prose / trailing commas keep working as before
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
        assert extract_json('Here you go: {"a": 1}') == {"a": 1}
        assert extract_json('{"a": [1, 2,],}') == {"a": [1, 2]}

    def test_hopeless_input_still_raises(self):
        with pytest.raises(Exception):
            extract_json("no json here at all")


class TestParseWithRetry:
    def test_good_text_never_retries(self):
        calls = []
        got = planner._parse_with_retry(
            '{"ok": 1}', lambda: calls.append(1) or ('{"x": 2}', None), "t")
        assert got == {"ok": 1}
        assert calls == []

    def test_bad_then_good_retries_once(self, capsys):
        # so hopeless that even layer 6 can't save it → retry fires
        got = planner._parse_with_retry(
            "utter garbage", lambda: ('{"fixed": true}', "end_turn"), "t")
        assert got == {"fixed": True}
        err = capsys.readouterr().err
        assert "unparseable model JSON" in err

    def test_bad_twice_raises_and_logs_both(self, capsys):
        with pytest.raises(Exception):
            planner._parse_with_retry(
                "garbage one", lambda: ("garbage two", "end_turn"), "t")
        err = capsys.readouterr().err
        assert "t:" in err and "t (retry):" in err

    def test_log_includes_failure_context(self, capsys):
        bad = '{"a": 1, "b": ' + "x" * 50 + "}"
        with pytest.raises(Exception):
            planner._parse_with_retry(bad, lambda: ("also bad", None), "ctx")
        err = capsys.readouterr().err
        assert "context @" in err        # position + surrounding text preserved
        assert "stop_reason" in err
