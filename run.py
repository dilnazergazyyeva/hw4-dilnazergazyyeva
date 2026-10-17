"""Run strategies on the questions and save everything to outputs/.

  python run.py --run 1 --strategy s3 --questions Q-09          # try one question first
  python run.py --run 1 --strategy all                          # full run
  python run.py --measure-tools                                 # tokens added by the two tool definitions
  python run.py --run 1 --strategy s3 --questions Q-01,Q-05 --vague --tag vague   # part C1

Prices ($ per 1M tokens) are not hard-coded: set PRICE_IN and PRICE_OUT from the official price page.
"""
import argparse
import json
import os
import statistics
import time
from pathlib import Path

import strategies as S

OUT = Path(__file__).parent / "outputs"
VAGUE = "Looks things up."


def run_one(strategy, q, docs, vague):
    t0 = time.perf_counter()
    if strategy == "s1":
        res = S.s1(q, docs)
    elif strategy == "s2":
        res = S.s2(q, docs)
    else:
        res = S.s3(q, VAGUE if vague else None)
    res["seconds"] = round(time.perf_counter() - t0, 3)
    res["id"], res["expected"] = q["id"], {"answer": q["answer"], "value": q["value"]}
    res["correct"] = S.is_correct(res["parsed"], q)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--strategy", default="all", choices=["s1", "s2", "s3", "all"])
    ap.add_argument("--questions", default="all")
    ap.add_argument("--vague", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--measure-tools", action="store_true")
    a = ap.parse_args()

    if a.measure_tools:
        import tools
        msgs = [{"role": "user", "content": "Say OK."}]
        u1, u2 = S.new_usage(), S.new_usage()
        S.chat(msgs, u1)
        S.chat(msgs, u2, tools_defs=tools.tool_definitions())
        d = u2["input_tokens"] - u1["input_tokens"]
        (OUT / "tool_definition_tokens.json").write_text(json.dumps(
            {"without_tools": u1["input_tokens"], "with_tools": u2["input_tokens"], "difference": d}, indent=2))
        print("tool definitions add", d, "input tokens per request")
        return

    questions = json.loads((Path(__file__).parent / "data" / "questions.json").read_text(encoding="utf-8"))
    if a.questions != "all":
        want = set(a.questions.split(","))
        questions = [q for q in questions if q["id"] in want]
    docs = S.load_docs()
    price_in, price_out = os.getenv("PRICE_IN"), os.getenv("PRICE_OUT")
    strats = ["s1", "s2", "s3"] if a.strategy == "all" else [a.strategy]
    rows = []
    for st in strats:
        folder = OUT / f"run{a.run}{('_' + a.tag) if a.tag else ''}" / st
        folder.mkdir(parents=True, exist_ok=True)
        results = []
        for q in questions:
            try:
                res = run_one(st, q, docs, a.vague)
            except Exception as e:  # log and continue; the question counts as unanswered
                res = {"id": q["id"], "error": f"{type(e).__name__}: {e}", "parsed": None, "correct": False,
                       "unanswered": True, "seconds": 0, "usage": S.new_usage()}
            (folder / f"{q['id']}.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
            results.append(res)
            print(st, q["id"], "OK " if res["correct"] else "BAD", res["parsed"], f"{res['seconds']}s")
        tin = sum(r["usage"]["input_tokens"] for r in results)
        tout = sum(r["usage"]["output_tokens"] for r in results)
        secs = [r["seconds"] for r in results]
        cost = round(tin / 1e6 * float(price_in) + tout / 1e6 * float(price_out), 4) if price_in and price_out else "set PRICE_IN/PRICE_OUT"
        row = {"run": a.run, "strategy": st, "correct": sum(r["correct"] for r in results), "n": len(results),
               "unanswered": sum(r["unanswered"] for r in results), "input_tokens": tin, "output_tokens": tout,
               "median_seconds": round(statistics.median(secs), 2), "total_seconds": round(sum(secs), 1), "cost_usd": cost,
               "temperature_rejected_by_model": S.TEMPERATURE_REJECTED}
        rows.append(row)
        (folder / "summary.json").write_text(json.dumps(row, indent=2))
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
