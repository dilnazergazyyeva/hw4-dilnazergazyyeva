import json
import pytest
from tools import lookup, calculate, run_tool, tool_definitions


# ---------------- lookup ----------------
def test_lookup_correct_2025_number():
    r = lookup("Millbrook", "population_2025")
    assert r["value"] == 37203 and r["source"] == "NR-11"


def test_lookup_case_and_spaces_ok():
    assert lookup("  ossbridge ", "area_km2")["value"] == 1284.6


def test_lookup_misspelled_name_suggests():
    r = lookup("Ossbrige", "population_2025")
    assert "error" in r and "Ossbridge" in r["error"]


def test_lookup_similar_names_not_mixed_up():
    a, b = lookup("Ossbridge", "population_2025"), lookup("Ossford", "population_2025")
    assert a["value"] == 52904 and b["value"] == 30982
    r = lookup("Oss", "population_2025")
    assert "error" in r and "Ossford" in r["error"] and "Ossbridge" in r["error"]


def test_lookup_archived_profile_not_used():
    assert lookup("Tarnvale", "population_2025")["value"] == 71388   # not the 2019 estimate 65,030
    r = lookup("Tarnvale", "population_2019")
    assert "error" in r and "archived" in r["error"]


def test_lookup_correction_notice_applied():
    r = lookup("Brightwater", "area_km2")
    assert r["value"] == 921.4 and "NR-16" in r["source"] and "note" in r


def test_lookup_water_unit_normalised():
    assert lookup("Lindenmoor", "water_use_m3")["value"] == 2151400
    assert lookup("Kelmarsh", "water_use_m3")["value"] == 1739000


def test_lookup_population_went_down_even_though_text_says_up():
    assert lookup("Stonecairn", "population_2025")["value"] == 14926
    assert lookup("Stonecairn", "population_2020")["value"] == 15473


def test_lookup_tariff_and_bad_inputs_never_crash():
    assert lookup("region", "water_tariff_tenge_per_m3")["value"] == 142.35
    for d, f in [(None, "area_km2"), ("Ossbridge", 5), ("", ""), ("Ossbridge", "colour"), ("x" * 100000, "schools")]:
        assert "error" in lookup(d, f)


# ---------------- calculate ----------------
def test_calc_example_from_brief():
    assert calculate("48317 * 1.0947")["result"] == pytest.approx(48317 * 1.0947, rel=1e-9)


def test_calc_division_and_precedence():
    assert calculate("44675 / 921.4")["result"] == pytest.approx(48.4859, abs=1e-3)
    assert calculate("2 + 3 * 4")["result"] == 14
    assert calculate("-(3 - 5) ** 2")["result"] == -4


@pytest.mark.parametrize("bad", ["__import__('os').system('echo hi')", "(1).__class__", "9**9**9",
                                 "open('x')", "[1,2]", "'a'*10", "x + 1", "lambda: 1", "1 if 1 else 2"])
def test_calc_refuses_dangerous(bad):
    r = calculate(bad)
    assert "error" in r and "result" not in r


def test_calc_division_by_zero_and_huge():
    assert "error" in calculate("1 / 0")
    assert "error" in calculate("10 ** 50")
    assert "error" in calculate("1" + "0" * 400)


def test_calc_bad_input_types_and_syntax():
    assert "error" in calculate(None)
    assert "error" in calculate("44,675 / 2")
    assert "error" in calculate("(" * 500 + "1" + ")" * 500)
    assert "error" in calculate("")


# ---------------- plumbing ----------------
def test_run_tool_always_returns_json_string():
    assert json.loads(run_tool("lookup", {"district": "Redfen", "field": "schools"}))["value"] == 10
    assert "error" in json.loads(run_tool("nope", {}))
    assert "error" in json.loads(run_tool("calculate", {}))


def test_tool_definitions_shape():
    defs = tool_definitions()
    assert [d["function"]["name"] for d in defs] == ["lookup", "calculate"]
