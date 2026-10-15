# HW4 — submission

**AI assistance:** I used Claude (Anthropic) to help draft Part A, `tools.py`, the tests, `strategies.py`, `run.py` and a first draft of the notes in this file. I read and checked the code, ran everything myself, and wrote Part C from my own logs. <!-- ✏️ EDIT THIS so it is exactly true for you. -->

---

## Part A — Plan on paper (Easy)

> Commit this whole part before any `.py` file exists.

### A1 — The steps

Task: *"Which district is denser, Brightwater or Millbrook, and by how much?"*

| # | Step | What goes in (types) | What comes out (types) | When it goes wrong | Tool, loop, or model? |
|---|---|---|---|---|---|
| 1 | **Plan**: decide which facts are needed and which operation to do | question `str` | list of `(district: str, field: str)` pairs + the formula in words | question not understood → the model asks for the wrong fact (caught later by step 3 errors) | model |
| 2 | **Find the district**: match the name to one of the 12 districts | `district: str` | canonical name `str` | misspelled → `{"error": "... did you mean X or Y?"}`; prefix matches two (`Oss`) → error listing both; empty / not a string → error | `lookup` tool |
| 3 | **Pick the right document**: take the 2025 profile, skip ARCHIVED ones, apply correction notices | canonical name `str`, `field: str` | `(raw_value: float, doc_ids: list[str])` | field unknown or asks for 2019/2018 → error with the valid field list; only an archived profile exists → error; corrected field (Brightwater area) → value from NR-16, with a note | `lookup` tool |
| 4 | **Read and normalise the number**: pull the number out of the sentence, convert units (megalitres → m³) | sentence `str` | `value: float`, `unit: str`, `source: str` | number cannot be parsed → error `"<field> not found for <district>"`; Lindenmoor reports m³, others megalitres → converted to m³ and noted | `lookup` tool |
| 5 | **Calculate** | `expression: str` | `result: float` | not an expression / unsafe → `refused`; `/ 0` → `refused: division by zero`; too big → `refused`; commas in numbers → syntax error with hint | `calculate` tool |
| 6 | **Round and answer**: compare, choose the name, round once at the end, write `ANSWER: <name> \| <number>` | numbers `float`, `decimals: int` | final text `str` | forgets the format line → counted as unanswered | model |
| 7 | **Run the requests**: read `arguments` (JSON string), validate, run the tool, send back a result for *every* `tool_call_id`, stop after the round limit | model message `tool_calls` | `tool` messages `list[dict]`; log entry per call | invalid JSON → error result (not a crash); unknown tool name → error result; round limit hit → question marked unanswered | loop (my code) |
| 8 | **Check the answer** against `questions.json` | `parsed (name, number)`, question `dict` | `correct: bool` | no `ANSWER:` line → `False` and `unanswered` | `run.py` |

**How the steps connect:**

```text
question ──► [1 plan: model] ──► (district, field) ──► [7 loop] ──► [2 find district] ──► [3 pick document]
                  ▲                                                                           │
                  │                                                                           ▼
                  │                                                              [4 read + normalise number]
                  │                                                                           │
                  │                              {"value","unit","source"} (or {"error"}) ◄───┘
                  │                                          │
                  └──────── tool message (same tool_call_id) ┘
model collects all values ──► [5 calculate: tool via loop] ──► result ──► [6 round + ANSWER line: model] ──► [8 check]
```

Steps 2–4 are one tool (`lookup`), step 5 is the other (`calculate`), 7 is the loop, 1 and 6 are the model, 8 is the scorer.
Every step has exactly one owner and no step does another step's job, so together they cover the whole task.

**What I am assuming:**

- Numbers are the **2025** census, the **2025** budget, the **2025/26** school year, and household water use in **calendar 2025** (as NR-00 says).
- **Archived** profiles (NR-13, NR-14) are never used. A **correction notice wins** over the profile it corrects (NR-16: Brightwater area is 921.4 km², not 912.4).
- Water: 1 megalitre = 1,000 m³ (NR-15). Lindenmoor is given in m³, so `lookup` returns all water use in m³. Litres per resident per day = m³ × 1000 ÷ population ÷ **365** (2025 is not a leap year).
- Water cost = m³ × **142.35 tenge** (the 2025 tariff, not the 2024 one).
- Growth % = (pop2025 − pop2020) ÷ pop2020 × 100. For projections the same % is applied once more to 2025.
- Wording like "up from" in a profile is **not trusted**: Stonecairn and Coldharbour say "up from" but their population fell. The numbers decide.
- **Rounding happens only once, at the very end** (the calculator keeps full precision).
- The assumption my solution is **most sensitive to**: that the right profile and the correction are chosen *inside the tool*, not left to the model. If the model chose, one wrong pick (e.g. an archived number) would silently break the answer.

### A2 — The two tools

#### `lookup`

```json
{
  "type": "function",
  "function": {
    "name": "lookup",
    "description": "Look up one fact about one district of the Nine Rivers Region (a made-up region). Returns the current 2025 value, its unit and the source document id. Archived 2019 profiles are ignored and correction notices are already applied. Call it once per (district, field). Water use is always returned in cubic metres. Use district='region' with field 'water_tariff_tenge_per_m3' to get the household water tariff. If the name is misspelled the tool returns an error with suggestions; call again with the right name.",
    "parameters": {
      "type": "object",
      "properties": {
        "district": {
          "type": "string",
          "description": "District name, e.g. 'Ossbridge', or 'region' for the tariff"
        },
        "field": {
          "type": "string",
          "enum": [
            "population_2025",
            "population_2020",
            "area_km2",
            "budget_million_tenge",
            "water_use_m3",
            "schools",
            "pupils_2025_26",
            "paved_road_km",
            "founded_year",
            "water_tariff_tenge_per_m3"
          ],
          "description": "Which fact to fetch"
        }
      },
      "required": [
        "district",
        "field"
      ],
      "additionalProperties": false
    }
  }
}
```

| Case | What the tool returns |
|---|---|
| success | `{"district": "Millbrook", "field": "population_2025", "value": 37203, "unit": "residents, 2025 census", "source": "NR-11"}` |
| corrected value | same, with `"source": "NR-05 + NR-16"` and a `"note"` saying the correction notice took precedence |
| water use | always in cubic metres; for Lindenmoor a `"note"` says the profile used m³ |
| misspelled district | `{"error": "no district named Ossbrige; did you mean Ossbridge or Ossford?"}` |
| ambiguous prefix (`Oss`) | error listing both `Ossbridge` and `Ossford` |
| unknown field | error with the closest field names and the full list |
| archived / 2019 / 2018 / "estimate" field | error: archived profiles are superseded, ask for a 2025 field |
| wrong type (`None`, number) or empty | `{"error": "district and field must both be strings"}` |
| any unexpected exception | `{"error": "lookup failed: <ExceptionName>"}` (never a crash) |

**Worst thing it could do with strange or dangerous input:** nothing dangerous: it only reads a dictionary built from `corpus.jsonl`, never opens a path or runs code from the input. The worst case is a useless error message (or, for a 100,000-character name, a slow fuzzy match, which is why long names are not an issue for 12 districts).

#### `calculate`

```json
{
  "type": "function",
  "function": {
    "name": "calculate",
    "description": "Evaluate an arithmetic expression exactly. Use it for EVERY calculation instead of computing in your head. Allowed: numbers, + - * / **, parentheses. Write numbers without commas, e.g. '44675 / 921.4'.",
    "parameters": {
      "type": "object",
      "properties": {
        "expression": {
          "type": "string",
          "description": "Arithmetic expression, e.g. '(37203 - 34590) / 34590 * 100'"
        }
      },
      "required": [
        "expression"
      ],
      "additionalProperties": false
    }
  }
}
```

| Case | What the tool returns |
|---|---|
| success | `{"expression": "44675 / 921.4", "result": 48.485999...}` |
| division by zero | `{"error": "refused: division by zero"}` |
| too large (`10**50`, exponent > 100, result > 1e18) | `{"error": "refused: ..."}` |
| unsafe syntax (`__import__`, `.attribute`, names, calls, strings, lists) | `{"error": "refused: Call is not allowed; use only numbers, + - * / ** and parentheses"}` |
| not valid Python (`44,675 / 2`) | `{"error": "could not read the expression; write plain numbers without commas"}` |
| longer than 200 chars / not a string | error |

**Worst thing it could do with strange or dangerous input:** I never use `eval`/`exec`. The expression is parsed by `ast` and only numbers, `+ - * / **` and unary minus are walked. The worst the model can do is make it return an error or burn a little CPU on a ≤200-character expression: powers are capped (exponent ≤ 100) and every intermediate number is capped (≤ 1e18), so `9**9**9` cannot freeze it.

### A3 — Q-09 by hand

Q-09: *Which district has the higher population density in 2025, Brightwater or Millbrook, and by how many residents per square kilometre?*

```json
[
  {"role": "user", "content": "Question: Which district has the higher population density in 2025, Brightwater or Millbrook, and by how many residents per square kilometre?\nRound the number to 1 decimal places.\nFinish your reply with exactly one last line: ANSWER: <name or yes/no> | <number>"},
  {"role": "assistant", "tool_calls": [
    {"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\": \"Brightwater\", \"field\": \"population_2025\"}"}},
    {"id": "call_2", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\": \"Brightwater\", \"field\": \"area_km2\"}"}},
    {"id": "call_3", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\": \"Millbrook\", \"field\": \"population_2025\"}"}},
    {"id": "call_4", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\": \"Millbrook\", \"field\": \"area_km2\"}"}}
  ]},
  {"role": "tool", "tool_call_id": "call_1", "content": "{\"district\": \"Brightwater\", \"field\": \"population_2025\", \"value\": 44675, \"unit\": \"residents, 2025 census\", \"source\": \"NR-05\"}"},
  {"role": "tool", "tool_call_id": "call_2", "content": "{\"district\": \"Brightwater\", \"field\": \"area_km2\", \"value\": 921.4, \"unit\": \"square kilometres\", \"source\": \"NR-05 + NR-16\", \"note\": \"profile NR-05 gives 912.4 but correction notice NR-16 takes precedence; corrected value used\"}"},
  {"role": "tool", "tool_call_id": "call_3", "content": "{\"district\": \"Millbrook\", \"field\": \"population_2025\", \"value\": 37203, \"unit\": \"residents, 2025 census\", \"source\": \"NR-11\"}"},
  {"role": "tool", "tool_call_id": "call_4", "content": "{\"district\": \"Millbrook\", \"field\": \"area_km2\", \"value\": 758.6, \"unit\": \"square kilometres\", \"source\": \"NR-11\"}"},
  {"role": "assistant", "tool_calls": [
    {"id": "call_5", "type": "function", "function": {"name": "calculate", "arguments": "{\"expression\": \"37203 / 758.6 - 44675 / 921.4\"}"}}
  ]},
  {"role": "tool", "tool_call_id": "call_5", "content": "{\"expression\": \"37203 / 758.6 - 44675 / 921.4\", \"result\": 0.5556561156405735}"},
  {"role": "assistant", "content": "Millbrook: 37203 / 758.6 ≈ 49.04 residents/km²; Brightwater (corrected area 921.4): 44675 / 921.4 ≈ 48.49. Difference ≈ 0.56.\nANSWER: Millbrook | 0.6"}
]
```

**My arithmetic:**

- Brightwater: area is **921.4** (NR-16 correction, not 912.4 from NR-05). Density = 44,675 ÷ 921.4 = **48.486** residents/km².
- Millbrook: 37,203 ÷ 758.6 = **49.042** residents/km².
- Millbrook is denser. Difference = 49.0417 − 48.4860 = **0.5557 → 0.6** (1 decimal). This matches `questions.json` (Millbrook, 0.6).
- If the typo (912.4) had been used: 44,675 ÷ 912.4 = 48.964 → difference 0.08 → rounds to 0.1, a wrong answer. That is the trap.

### A4 — Why I split it this way

**Other split I did not choose:** one tool per kind of question (`density(a, b)`, `water_per_resident(a, b)`, `budget_per_pupil(a, b)`, ...), each doing lookup *and* arithmetic inside.
Why not: (1) the 20 questions use many different formulas, so I would need many tools, each with its own bugs and its own description the model must choose between; (2) the arithmetic would be hidden inside the tools and I could not see or check what the model asked for; (3) a new kind of question would need new code, while `lookup` + `calculate` handle any combination of facts and arithmetic. The cost of my split is more rounds (many small calls), which I accept for flexibility and for logs that show every step.

---

## Part B — Build it and run it (Medium)

### What I changed from Part A while coding

None so far. <!-- ✏️ If you change a tool, the loop or the rules while you test, write what and why here. Do NOT edit Part A. -->

### B2 — Tests

```text
<!-- ✏️ run: python -m pytest -v   and paste the real output here -->
```

### B3 — The loop

- Round limit, and why: **12 rounds**. Parallel calls count as one round. The hardest question (e.g. Q-20, three districts × two fields, then one or two calculations) needs about 3–4 rounds when the model batches calls and about 8–9 if it calls one tool at a time, so 12 leaves room for one or two retries after an error but still stops a loop that never ends (each round also costs more, because the whole conversation is sent again).
- Where the logs are: `outputs/run<N>/s3/Q-xx.json` (every tool call: round, id, tool, arguments, result, seconds), plus `outputs/run<N>/<strategy>/summary.json`.
- Real Q-09 conversation compared with my A3 version, what is different: <!-- ✏️ open outputs/run1/s3/Q-09.json and write what differs: number of rounds, were calls batched, did it call calculate once or several times, did it make an error? -->

### B4 — Three strategies

**What I kept the same:** model `gpt-5.6-luna` for everything; same 20 questions in the same order; same system sentence about the Nine Rivers Region; same question text, same "round to N decimals" line (taken from `decimals` in `questions.json`, never the answer) and same final line `ANSWER: <name or yes/no> | <number>`; S1 and S2 get the same 17 documents (all of them, archived ones included); S3 gets no documents; same parser and same scorer; `k = 5` and `temperature = 1.0` for S2 only (S1 and S3 use the model default); S3 round limit 12. <!-- ✏️ add: did the model accept temperature? (outputs/.../summary.json -> temperature_rejected_by_model). Add anything else you changed. -->

**My rule for a correct answer** (written before the first full run): the name (or yes/no) must equal the expected `answer`, ignoring upper/lower case; and the number, rounded to `decimals`, must equal `value` rounded to `decimals`, allowing a difference of 1 in the last digit (so 0.6 vs 0.5 or 0.7 counts for Q-09). An answer with no `ANSWER:` line, or an S3 run that hits the round limit, counts as unanswered and wrong. (Why 1 digit of tolerance: the model rounds its own numbers and a tiny rounding difference is not a reasoning error. Why 20 questions: that is what the course provides; see C4 for how little it can prove.)

| Run | Strategy | Correct /20 | Unanswered | Input tokens | Output tokens | Median seconds per question | Total seconds | Cost ($) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | S1 direct | | | | | | | |
| 1 | S2 think and vote (k = 5) | | | | | | | |
| 1 | S3 tools | | | | | | | |
| 2 | S1 direct | | | | | | | |
| 2 | S2 think and vote (k = 5) | | | | | | | |
| 2 | S3 tools | | | | | | | |

<!-- ✏️ Fill from outputs/run1/*/summary.json and outputs/run2/*/summary.json. Set PRICE_IN and PRICE_OUT (USD per 1M tokens, from the official price page) before running so the cost column is computed. -->

**Per question (run 1):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | | | |
| Q-02 | | | |
| Q-03 | | | |
| Q-04 | | | |
| Q-05 | | | |
| Q-06 | | | |
| Q-07 | | | |
| Q-08 | | | |
| Q-09 | | | |
| Q-10 | | | |
| Q-11 | | | |
| Q-12 | | | |
| Q-13 | | | |
| Q-14 | | | |
| Q-15 | | | |
| Q-16 | | | |
| Q-17 | | | |
| Q-18 | | | |
| Q-19 | | | |
| Q-20 | | | |

---

## Part C — Explain and choose (Hard)

> ✏️ **All of Part C must be written by you, from your own logs.** The rubric gives points only for your numbers, question ids and quotes. Hints are in the comments.

### C1 — Does the tool description matter?

<!-- Run: python run.py --run 1 --strategy s3 --questions Q-01,Q-05,Q-09,Q-14,Q-20 --vague --tag vague  (the vague description is "Looks things up.") -->

| Question | Calls (your description) | Calls (vague) | Answer (yours) | Answer (vague) |
|---|---:|---:|---|---|
| | | | | |

<!-- What changed: number of calls, inputs (did it still use the right field names? note the schema enum still shows them), answers. Why? -->

### C2 — Three mistakes explained

<!-- One wrong answer per strategy (or the most expensive question if a strategy got everything right). Quote your logs (outputs/run1/<strategy>/Q-xx.json). Think about: why voting fixes random slips but not a systematic mistake (e.g. the same wrong document used 5 times); why a calculator removes errors (the model predicts digits, the tool computes them); why rounds cost more each time (the whole history is sent again). -->

### C3 — Which strategy I would use, and what would change it

<!-- Compare accuracy, tokens, time; say why you did not choose each other strategy; give at least two situations that change the choice (small budget, strict time limit, 1,000x more documents, no arithmetic) and the strategy for each. -->

### C4 — How sure I can be

<!-- How different were run 1 and run 2? Is the gap between the two best strategies bigger than that? With 20 questions, one question = 5 percentage points. How many questions would you want? -->

### Final questions

1. When the model sends a `tool_calls` message, **nothing has run yet**. The message is only a request: the model wrote the function name and its arguments as text. My code decides whether to run anything, runs it, and sends the result back; the model never executes code itself.
2. `arguments` arrives as a **string** of JSON because the API returns plain text from the model and the model can write anything. If I pass the string straight into my function, Python would treat it as one big string (not `district` and `field`), and invalid JSON, missing keys or wrong types could crash the program. So I run `json.loads`, check it is a dict, and return an error message to the model if it is not.
3. <!-- ✏️ run: python run.py --measure-tools   -> outputs/tool_definition_tokens.json. Write the number. -->
4. <!-- ✏️ S2 input tokens ÷ S1 input tokens, and cost ratio, from your table. Explain: S2 sends the same 2,300-token documents 5 times and each reply is longer because the model writes its reasoning. -->
5. <!-- ✏️ find it: look at the "rounds" field in outputs/run1/s3/*.json, pick the biggest, say why (many facts needed? errors? retries?). -->
6. With 100,000 documents I could not parse the whole corpus into memory on each call or put it in the prompt. I would build the index once (for example a search index or a table of facts extracted in advance, or embeddings with BM25), have `lookup` return only the top few short matches, and keep the archived/corrections rules as filters on metadata so they are applied by code and not by the model.
7. `calculate` never calls `eval`/`exec`: it parses with `ast` and only walks nodes for numbers, `+ - * / **` and unary signs, so anything else (calls, attributes, names, strings) is refused. Limits on length (200 chars), exponent (≤ 100) and size (≤ 1e18) stop freezing. The model can still make it misbehave in small ways: send a very long chain of allowed operations, ask for wrong formulas (a correct tool does not stop a wrong expression), or loop forever, which is why the loop has a round limit.
8. <!-- ✏️ From your own results: which questions did S3 win (many steps and arithmetic, e.g. growth, per-person costs?) and which did tools not help (e.g. Q-10, a simple comparison of founding years, or a question the model already got right in S1)? Name question ids. -->
