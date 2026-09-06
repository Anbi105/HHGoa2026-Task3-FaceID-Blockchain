"""Stage 3 — deterministic canonical serialization (§7)."""

import pytest

from faceproof.canonical import DEFAULT_PRECISION, _reject_floats, canon, q


def test_sorted_keys_and_compact():
    assert canon({"b": "2", "a": "1"}) == b'{"a":"1","b":"2"}'
    out = canon({"z": 1, "a": [1, 2, {"d": "x", "c": "y"}]}).decode()
    assert " " not in out and "\n" not in out
    assert out == '{"a":[1,2,{"c":"y","d":"x"}],"z":1}'


def test_key_order_independent():
    assert canon({"a": 1, "b": 2, "c": [1, 2]}) == canon({"c": [1, 2], "b": 2, "a": 1})


def test_utf8_not_escaped():
    raw = canon({"msg": "café ✨ 😀"})
    assert "café ✨ 😀".encode("utf-8") in raw
    assert b"\\u" not in raw


def test_rejects_bare_float():
    with pytest.raises(TypeError, match="raw float at"):
        canon({"bad": 0.5})
    with pytest.raises(TypeError, match=r"raw float at \$\.g\.v\[2\]"):
        canon({"g": {"v": [1, 2, 3.14]}})


def test_rejects_non_string_key():
    with pytest.raises(TypeError, match="non-string mapping key"):
        canon({1: "x"})


def test_q_is_fixed_precision_string():
    assert q(0.1234567) == "0.123457"
    assert q(1) == "1.000000"
    assert q("0.5") == "0.500000"
    assert q(3.14159265, nd=2) == "3.14"
    assert len(q(0.1).split(".")[1]) == DEFAULT_PRECISION


def test_q_output_survives_canon():
    # a value formatted with q() must never trip the float rejection
    canon({"score": q(0.87321)})


def test_reproducible_bytes():
    obj = {"groups": {"probe": {"commitment": "0x" + "ab" * 32, "det_score": q(0.9)}}}
    assert canon(obj) == canon(dict(obj))
