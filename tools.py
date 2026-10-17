"""Two tools for the model: `lookup` (facts from the corpus) and `calculate` (safe arithmetic).

Neither function ever raises: every problem comes back as {"error": "..."} so the model can read it.
"""
import ast
import difflib
import json
import operator
import re
from pathlib import Path

CORPUS_PATH = Path(__file__).parent / "data" / "corpus.jsonl"

# ----------------------------------------------------------------------------
# lookup
# ----------------------------------------------------------------------------
FIELDS = {
    "population_2025": "residents, 2025 census",
    "population_2020": "residents, 2020 census",
    "area_km2": "square kilometres",
    "budget_million_tenge": "million tenge, 2025 budget",
    "water_use_m3": "cubic metres, household water use in 2025",
    "schools": "schools",
    "pupils_2025_26": "pupils enrolled in 2025/26",
    "paved_road_km": "km of paved road",
    "founded_year": "year founded",
    "water_tariff_tenge_per_m3": "tenge per cubic metre (same in every district; use district='region')",
}
REGION_NAMES = {"region", "nine rivers region", "all", "all districts"}


def _num(s):
    return float(s.replace(",", ""))


def _first(patterns, text):
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m
    return None


def _parse_profile(text):
    """Pull the 2025 facts out of one district profile. The profiles use three different templates."""
    f = {}
    m = _first([r"founded in (\d{4})"], text)
    if m:
        f["founded_year"] = int(m.group(1))
    m = _first([r"([\d,\.]+) square kilometres"], text)
    if m:
        f["area_km2"] = _num(m.group(1))
    m = _first([r"budget for 2025 was set at ([\d,\.]+) million", r"2025 budget (?:amounted to|was) ([\d,\.]+) million"], text)
    if m:
        f["budget_million_tenge"] = _num(m.group(1))
    m = re.search(r"([\d,]+) megalitres", text)
    if m:
        f["water_use_m3"] = _num(m.group(1)) * 1000
        f["_water_note"] = None
    else:
        m = re.search(r"([\d,]+) cubic metres of water", text)
        if m:
            f["water_use_m3"] = _num(m.group(1))
            f["_water_note"] = "this profile publishes water use in cubic metres, not megalitres"
    m = _first([r"(?:There are|has|runs) (\d+) schools"], text)
    if m:
        f["schools"] = int(m.group(1))
    m = re.search(r"([\d,]+) pupils", text)
    if m:
        f["pupils_2025_26"] = int(_num(m.group(1)))
    m = _first([r"([\d,\.]+) km (?:long|of paved road)"], text)
    if m:
        f["paved_road_km"] = _num(m.group(1))
    # population: three templates, different order of the two years.
    m = re.search(r"2025 census recorded ([\d,]+) residents; the 2020 census had recorded ([\d,]+)", text)
    if m:
        f["population_2025"], f["population_2020"] = _num(m.group(1)), _num(m.group(2))
    else:
        m = re.search(r"Census population: ([\d,]+) in 2020 and ([\d,]+) in 2025", text)
        if m:
            f["population_2020"], f["population_2025"] = _num(m.group(1)), _num(m.group(2))
        else:
            # NB: the text says "up from" even when the number went down, so never trust the words.
            m = re.search(r"2025 census counted ([\d,]+) residents, \w+ from ([\d,]+) at the 2020 census", text)
            if m:
                f["population_2025"], f["population_2020"] = _num(m.group(1)), _num(m.group(2))
    return f


_DB = None


def _load():
    global _DB
    if _DB is not None:
        return _DB
    docs = [json.loads(l) for l in CORPUS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    districts, corrections, tariff = {}, {}, None
    for d in docs:
        title, text = d["title"], d["text"]
        if "ARCHIVED" in title:
            continue  # superseded 2019 profiles are never served
        m = re.match(r"(\w+) district profile \(2025\)", title)
        if m:
            districts[m.group(1)] = {"source": d["id"], "facts": _parse_profile(text)}
            continue
        m = re.match(r"Correction notice - (\w+)", title)
        if m:
            a = re.search(r"correct area is ([\d,\.]+) square kilometres", text)
            if a:
                corrections[m.group(1)] = {"source": d["id"], "area_km2": _num(a.group(1))}
            continue
        if "water tariff" in title.lower():
            t = re.search(r"tariff is ([\d,\.]+) tenge per cubic metre", text)
            if t:
                tariff = {"source": d["id"], "value": _num(t.group(1))}
    _DB = {"districts": districts, "corrections": corrections, "tariff": tariff}
    return _DB


def _clean(v):
    return int(v) if float(v).is_integer() else v


def lookup(district, field):
    """Return one 2025 fact about one district, with its source document. Never raises."""
    try:
        if not isinstance(district, str) or not isinstance(field, str):
            return {"error": "district and field must both be strings"}
        db = _load()
        field = field.strip().lower()
        q = district.strip()
        if any(w in field for w in ("2019", "2018", "archiv", "estimate")):
            return {"error": "archived 2019 profiles (NR-13, NR-14) are superseded and not available; "
                             "ask for a 2025 field. Valid fields: " + ", ".join(FIELDS)}
        if field not in FIELDS:
            close = difflib.get_close_matches(field, FIELDS, n=2, cutoff=0.5)
            hint = f"; did you mean {' or '.join(close)}?" if close else ""
            return {"error": f"unknown field '{field}'{hint} Valid fields: " + ", ".join(FIELDS)}
        if field == "water_tariff_tenge_per_m3":
            t = db["tariff"]
            if t is None:
                return {"error": "tariff not found in corpus"}
            if q.lower() not in REGION_NAMES and q.title() not in db["districts"]:
                return {"error": "the tariff is the same everywhere; use district='region'"}
            return {"district": "region", "field": field, "value": _clean(t["value"]),
                    "unit": FIELDS[field], "source": t["source"]}
        if q.lower() in REGION_NAMES:
            return {"error": "district='region' only works with field water_tariff_tenge_per_m3"}
        names = list(db["districts"])
        match = next((n for n in names if n.lower() == q.lower()), None)
        if match is None:
            cand = [n for n in names if q and n.lower().startswith(q.lower())]
            for n in difflib.get_close_matches(q.title(), names, n=3, cutoff=0.6):
                if n not in cand:
                    cand.append(n)
            hint = f"; did you mean {' or '.join(cand)}?" if cand else "; valid districts: " + ", ".join(names)
            return {"error": f"no district named {q}{hint}"}
        rec = db["districts"][match]
        value = rec["facts"].get(field)
        if value is None:
            return {"error": f"{field} not found for {match}"}
        out = {"district": match, "field": field, "value": _clean(value), "unit": FIELDS[field],
               "source": rec["source"]}
        corr = db["corrections"].get(match)
        if corr and field in corr:
            out["note"] = (f"profile {rec['source']} gives {_clean(value)} but correction notice {corr['source']} "
                           f"takes precedence; corrected value used")
            out["value"] = _clean(corr[field])
            out["source"] = f"{rec['source']} + {corr['source']}"
        if field == "water_use_m3" and rec["facts"].get("_water_note"):
            out["note"] = rec["facts"]["_water_note"] + "; value is already in cubic metres"
        return out
    except Exception as e:  # never crash
        return {"error": f"lookup failed: {type(e).__name__}"}


# ----------------------------------------------------------------------------
# calculate
# ----------------------------------------------------------------------------
MAX_LEN = 200       # characters in the expression
MAX_ABS = 1e18      # biggest number we accept at any step (the data never needs more)
MAX_EXP = 100       # biggest exponent in a power
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class _Refuse(Exception):
    pass


def _check(v):
    if isinstance(v, complex) or v != v or abs(v) > MAX_ABS:
        raise _Refuse("number too large or not a real number")
    return v


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if type(node.value) in (int, float):
            return _check(node.value)
        raise _Refuse("only numbers are allowed")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        a, b = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Div) and b == 0:
            raise _Refuse("division by zero")
        if isinstance(node.op, ast.Pow) and abs(b) > MAX_EXP:
            raise _Refuse(f"exponent larger than {MAX_EXP} is not allowed")
        return _check(_BIN[type(node.op)](a, b))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
        return _check(_UN[type(node.op)](_eval(node.operand)))
    raise _Refuse(f"{type(node).__name__} is not allowed; use only numbers, + - * / ** and parentheses")


def calculate(expression):
    """Safely evaluate an arithmetic expression. Never uses eval/exec. Never raises."""
    try:
        if not isinstance(expression, str):
            return {"error": "expression must be a string"}
        if len(expression) > MAX_LEN:
            return {"error": f"expression longer than {MAX_LEN} characters"}
        tree = ast.parse(expression.strip(), mode="eval")
        value = float(_eval(tree))
        return {"expression": expression, "result": value}
    except _Refuse as e:
        return {"error": f"refused: {e}"}
    except SyntaxError:
        return {"error": "could not read the expression; write plain numbers without commas, e.g. 44675 / 921.4"}
    except ZeroDivisionError:
        return {"error": "refused: division by zero"}
    except (OverflowError, RecursionError, MemoryError, ValueError):
        return {"error": "refused: number too large or expression too complicated"}
    except Exception as e:
        return {"error": f"calculate failed: {type(e).__name__}"}


# ----------------------------------------------------------------------------
# definitions sent to the model + dispatcher used by the loop
# ----------------------------------------------------------------------------
LOOKUP_DESCRIPTION = (
    "Look up one fact about one district of the Nine Rivers Region (a made-up region). "
    "Returns the current 2025 value, its unit and the source document id. Archived 2019 profiles are "
    "ignored and correction notices are already applied. Call it once per (district, field). "
    "Water use is always returned in cubic metres. Use district='region' with field "
    "'water_tariff_tenge_per_m3' to get the household water tariff. "
    "If the name is misspelled the tool returns an error with suggestions; call again with the right name."
)
CALCULATE_DESCRIPTION = (
    "Evaluate an arithmetic expression exactly. Use it for EVERY calculation instead of computing in your head. "
    "Allowed: numbers, + - * / **, parentheses. Write numbers without commas, e.g. '44675 / 921.4'."
)


def tool_definitions(lookup_description=LOOKUP_DESCRIPTION):
    return [
        {"type": "function", "function": {
            "name": "lookup", "description": lookup_description,
            "parameters": {"type": "object", "properties": {
                "district": {"type": "string", "description": "District name, e.g. 'Ossbridge', or 'region' for the tariff"},
                "field": {"type": "string", "enum": list(FIELDS), "description": "Which fact to fetch"}},
                "required": ["district", "field"], "additionalProperties": False}}},
        {"type": "function", "function": {
            "name": "calculate", "description": CALCULATE_DESCRIPTION,
            "parameters": {"type": "object", "properties": {
                "expression": {"type": "string", "description": "Arithmetic expression, e.g. '(37203 - 34590) / 34590 * 100'"}},
                "required": ["expression"], "additionalProperties": False}}},
    ]


def run_tool(name, args):
    """args is an already-parsed dict. Returns a JSON string."""
    if name == "lookup":
        if not isinstance(args, dict) or "district" not in args or "field" not in args:
            return json.dumps({"error": "lookup needs 'district' and 'field'"})
        return json.dumps(lookup(args["district"], args["field"]))
    if name == "calculate":
        if not isinstance(args, dict) or "expression" not in args:
            return json.dumps({"error": "calculate needs 'expression'"})
        return json.dumps(calculate(args["expression"]))
    return json.dumps({"error": f"unknown tool '{name}'; available: lookup, calculate"})
