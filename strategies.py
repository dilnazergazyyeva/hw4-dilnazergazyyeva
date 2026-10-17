"""The three strategies. Same model, same questions, same answer format; only the strategy differs."""
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

import tools

MODEL = "gpt-5.6-luna"
K = 5                 # S2 samples per question
S2_TEMPERATURE = 1.0  # needed so the 5 samples can differ (dropped automatically if the model refuses it)
MAX_ROUNDS = 12       # S3 round limit
DATA = Path(__file__).parent / "data"

_client = None
TEMPERATURE_REJECTED = False


def client():
    global _client
    if _client is None:
        from dotenv import load_dotenv
        from openai import OpenAI
        load_dotenv()
        _client = OpenAI()  # reads OPENAI_API_KEY from the environment; the key is never printed or logged
    return _client


# ---------------------------------------------------------------- prompts
def load_docs():
    docs = [json.loads(l) for l in (DATA / "corpus.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return "\n\n".join(f"[{d['id']}] {d['title']}\n{d['text']}" for d in docs)


FORMAT_RULE = ("Finish your reply with exactly one last line in this form:\n"
               "ANSWER: <name or yes/no> | <number>\n"
               "Use the district name alone (e.g. 'Millbrook') or 'yes'/'no'. The number has no units and no commas.")


def question_block(q):
    return f"Question: {q['question']}\nRound the number to {q['decimals']} decimal places.\n{FORMAT_RULE}"


SYSTEM_DOCS = ("You answer questions about the Nine Rivers Region, a made-up region. Use only the documents "
               "provided; you have no other knowledge of it.")
SYSTEM_TOOLS = ("You answer questions about the Nine Rivers Region, a made-up region. You have no documents. "
                "Get every fact with the lookup tool and do every calculation with the calculate tool. "
                "Do not guess and do not do arithmetic in your head.")


# ---------------------------------------------------------------- one API call with bookkeeping
def chat(messages, usage, tools_defs=None, temperature=None):
    global TEMPERATURE_REJECTED
    kw = dict(model=MODEL, messages=messages)
    if tools_defs:
        kw["tools"] = tools_defs
    if temperature is not None and not TEMPERATURE_REJECTED:
        kw["temperature"] = temperature
    t0 = time.perf_counter()
    try:
        r = client().chat.completions.create(**kw)
    except Exception as e:
        if "temperature" in kw and "temperature" in str(e).lower():
            TEMPERATURE_REJECTED = True  # the model does not allow it: retry once without
            kw.pop("temperature")
            r = client().chat.completions.create(**kw)
        else:
            raise
    usage["calls"] += 1
    usage["input_tokens"] += r.usage.prompt_tokens
    usage["output_tokens"] += r.usage.completion_tokens
    return r, time.perf_counter() - t0


def new_usage():
    return {"calls": 0, "input_tokens": 0, "output_tokens": 0}


# ---------------------------------------------------------------- answer parsing and scoring
_ANS = re.compile(r"ANSWER:\s*(.+?)\s*\|\s*(-?[\d.,\s]*\d)", re.I)


def parse_answer(text):
    """Returns (name_lowercase, number) from the last ANSWER line, or None."""
    for line in reversed((text or "").strip().splitlines()):
        m = _ANS.search(line)
        if m:
            try:
                return m.group(1).strip().strip("*").lower(), float(re.sub(r"[,\s]", "", m.group(2)))
            except ValueError:
                return None
    return None


def is_correct(parsed, q):
    """Rule (fixed before the first full run): name equal (case-insensitive) AND number equal to q['value']
    rounded to q['decimals'], allowing a difference of 1 in the last digit."""
    if parsed is None:
        return False
    name, num = parsed
    d = q["decimals"]
    return name == q["answer"].lower() and abs(round(num, d) - round(q["value"], d)) <= 10 ** -d * 1.0001


# ---------------------------------------------------------------- S1
def s1(q, docs):
    usage = new_usage()
    msgs = [{"role": "system", "content": SYSTEM_DOCS},
            {"role": "user", "content": f"Documents:\n\n{docs}\n\n{question_block(q)}"}]
    r, dt = chat(msgs, usage)
    text = r.choices[0].message.content
    return {"raw": text, "parsed": parse_answer(text), "usage": usage, "unanswered": parse_answer(text) is None}


# ---------------------------------------------------------------- S2
def s2(q, docs):
    usage = new_usage()
    msgs = [{"role": "system", "content": SYSTEM_DOCS},
            {"role": "user", "content": f"Documents:\n\n{docs}\n\nThink step by step, then answer.\n{question_block(q)}"}]
    samples = []
    for _ in range(K):
        r, dt = chat(msgs, usage, temperature=S2_TEMPERATURE)
        text = r.choices[0].message.content
        samples.append({"raw": text, "parsed": parse_answer(text)})
    votes = Counter((p[0], round(p[1], q["decimals"])) for s in samples if (p := s["parsed"]))
    winner = votes.most_common(1)[0][0] if votes else None
    return {"samples": samples, "votes": [[list(k), v] for k, v in votes.most_common()],
            "parsed": winner, "usage": usage, "unanswered": winner is None,
            "temperature_used": None if TEMPERATURE_REJECTED else S2_TEMPERATURE}


# ---------------------------------------------------------------- S3
def s3(q, lookup_description=None):
    usage = new_usage()
    defs = tools.tool_definitions(lookup_description) if lookup_description else tools.tool_definitions()
    msgs = [{"role": "system", "content": SYSTEM_TOOLS}, {"role": "user", "content": question_block(q)}]
    log, text, rounds = [], None, 0
    for rounds in range(1, MAX_ROUNDS + 1):
        r, dt = chat(msgs, usage, tools_defs=defs)
        msg = r.choices[0].message
        if not msg.tool_calls:
            text = msg.content
            break
        msgs.append(msg)  # the model's message, with its tool_calls, goes back unchanged
        for tc in msg.tool_calls:  # answer EVERY tool_call_id
            t0 = time.perf_counter()
            try:
                args = json.loads(tc.function.arguments)  # arrives as a string
                if not isinstance(args, dict):
                    raise ValueError("arguments must be a JSON object")
                result = tools.run_tool(tc.function.name, args)
            except (json.JSONDecodeError, ValueError) as e:
                result = json.dumps({"error": f"arguments were not valid JSON: {e}"})
            log.append({"round": rounds, "id": tc.id, "tool": tc.function.name, "arguments": tc.function.arguments,
                        "result": result, "seconds": round(time.perf_counter() - t0, 6)})
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    parsed = parse_answer(text) if text else None
    return {"raw": text, "parsed": parsed, "usage": usage, "rounds": rounds, "tool_calls": log,
            "hit_round_limit": text is None, "unanswered": parsed is None}
