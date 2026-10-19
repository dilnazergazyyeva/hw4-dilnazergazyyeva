# HW4 — submission

**AI assistance:** I used Claude (Anthropic) to draft Part A, the code (`tools.py`, `strategies.py`, `run.py`), the tests and the first draft of the written answers in this file. I ran the code and the tests myself, with my own API key, and the numbers below come from my own runs in `outputs/`.

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

Two things, both forced by the environment, not by the plan.

- I added `reasoning_effort="none"` to every request. Without it the API refuses to use tools with this model in Chat Completions (a 400 error that says so). I set it for all three strategies, so the comparison stays fair.
- I save result files as UTF-8. On Windows the first S1 test crashed when the model wrote the sign ÷ in its answer.

The tools and the loop work as I planned in A2 and A3.

### B2 — Tests

```text
================================================== test session starts ==================================================
platform win32 -- Python 3.13.15, pytest-9.1.1, pluggy-1.7.0 -- C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\user\ai hw\hw4-dilnazergazyyeva
plugins: anyio-4.10.0
collected 24 items

tests/test_tools.py::test_lookup_correct_2025_number PASSED                                                        [  4%]
tests/test_tools.py::test_lookup_case_and_spaces_ok PASSED                                                         [  8%]
tests/test_tools.py::test_lookup_misspelled_name_suggests PASSED                                                   [ 12%]
tests/test_tools.py::test_lookup_similar_names_not_mixed_up PASSED                                                 [ 16%]
tests/test_tools.py::test_lookup_archived_profile_not_used PASSED                                                  [ 20%]
tests/test_tools.py::test_lookup_correction_notice_applied PASSED                                                  [ 25%]
tests/test_tools.py::test_lookup_water_unit_normalised PASSED                                                      [ 29%]
tests/test_tools.py::test_lookup_population_went_down_even_though_text_says_up PASSED                              [ 33%]
tests/test_tools.py::test_lookup_tariff_and_bad_inputs_never_crash PASSED                                          [ 37%]
tests/test_tools.py::test_calc_example_from_brief PASSED                                                           [ 41%]
tests/test_tools.py::test_calc_division_and_precedence PASSED                                                      [ 45%]
tests/test_tools.py::test_calc_refuses_dangerous[__import__('os').system('echo hi')] PASSED                        [ 50%]
tests/test_tools.py::test_calc_refuses_dangerous[(1).__class__] PASSED                                             [ 54%]
tests/test_tools.py::test_calc_refuses_dangerous[9**9**9] PASSED                                                   [ 58%]
tests/test_tools.py::test_calc_refuses_dangerous[open('x')] PASSED                                                 [ 62%]
tests/test_tools.py::test_calc_refuses_dangerous[[1,2]] PASSED                                                     [ 66%]
tests/test_tools.py::test_calc_refuses_dangerous['a'*10] PASSED                                                    [ 70%]
tests/test_tools.py::test_calc_refuses_dangerous[x + 1] PASSED                                                     [ 75%]
tests/test_tools.py::test_calc_refuses_dangerous[lambda: 1] PASSED                                                 [ 79%]
tests/test_tools.py::test_calc_refuses_dangerous[1 if 1 else 2] PASSED                                             [ 83%]
tests/test_tools.py::test_calc_division_by_zero_and_huge PASSED                                                    [ 87%]
tests/test_tools.py::test_calc_bad_input_types_and_syntax PASSED                                                   [ 91%]
tests/test_tools.py::test_run_tool_always_returns_json_string PASSED                                               [ 95%]
tests/test_tools.py::test_tool_definitions_shape PASSED                                                            [100%]

================================================== 24 passed in 0.86s ===================================================
```

### B3 — The loop

- Round limit, and why: 12 rounds. One round is one call to the model, and parallel tool calls count as one round. I chose 12 before I knew how many I would need, to leave room for retries after errors and still stop a loop that never ends. In practice it was far more than enough: every S3 question I checked took 3 or 4 rounds, and none hit the limit (0 unanswered in both runs). The model asks for all the facts it needs in one round, then for the calculations, then answers.
- Where the logs are: `outputs/run1/s3/Q-xx.json` and `outputs/run2/s3/Q-xx.json`. Each has every tool call with its round, id, tool name, arguments, result and seconds. `summary.json` in each folder has the totals.
- Real Q-09 conversation compared with my A3 version, what is different: the real conversation (`outputs/run1/s3/Q-09.json`) had 4 rounds and 7 tool calls, and in A3 I wrote 3 model turns and 5 calls. The lookups were the same as in my plan: four of them in round 1, with the same results, including 921.4 for the Brightwater area and the note about the correction notice NR-16. The difference is in the arithmetic. I planned one `calculate` call for the whole expression. The model made two (`44675 / 921.4` and `37203 / 758.6`, in parallel, in round 2) and then a third call in round 3 to subtract the two results (`49.041655681518584 - 48.48599956587801`, which returned 0.5556561156405735). Round 4 was the answer, `ANSWER: Millbrook | 0.6`. So it split the calculation into small steps, which costs one more round but is easy to follow in the log.

### B4 — Three strategies

**What I kept the same:** model `gpt-5.6-luna` for everything, with `reasoning_effort="none"`. The same 20 questions in the same order. The same one-sentence system prompt about the Nine Rivers Region. The same question text, the same line "Round the number to N decimal places" (N comes from `decimals` in `questions.json`, never from the answer) and the same last line `ANSWER: <name or yes/no> | <number>`. S1 and S2 get the same 17 documents, archived ones included, and S3 gets none. The same parser and the same scorer. S2 uses k = 5 and temperature 1.0. The model accepted the temperature (`temperature_rejected_by_model` is false), and S1 and S3 use the default. The S3 round limit is 12. Prices I used for cost: $0.20 per 1M input tokens and $1.20 per 1M output tokens. Both full runs together cost about $0.17.

**My rule for a correct answer** (written before the first full run): the name (or yes/no) must be equal to the expected answer, ignoring capital letters. The number, rounded to `decimals`, must equal `value` rounded to `decimals`, with a difference of 1 in the last digit allowed. A reply without an `ANSWER:` line, or an S3 run that hits the round limit, is unanswered and wrong. I allow one digit because the model rounds by itself, and a tiny rounding gap is not a reasoning mistake. I used 20 questions because that is what the course gives. C4 says how little that proves.

| Run | Strategy | Correct /20 | Unanswered | Input tokens | Output tokens | Median seconds per question | Total seconds | Cost ($) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | S1 direct | 16 | 0 | 44279 | 1772 | 1.67 | 34.7 | 0.0110 |
| 1 | S2 think and vote (k = 5) | 16 | 0 | 222195 | 9070 | 7.99 | 160.5 | 0.0553 |
| 1 | S3 tools | 20 | 0 | 57635 | 4341 | 4.68 | 99.7 | 0.0167 |
| 2 | S1 direct | 13 | 0 | 44279 | 1705 | 1.63 | 33.9 | 0.0109 |
| 2 | S2 think and vote (k = 5) | 17 | 0 | 222195 | 9166 | 7.43 | 152.5 | 0.0554 |
| 2 | S3 tools | 20 | 0 | 60033 | 4452 | 4.93 | 96.0 | 0.0173 |

**Per question (run 1):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | ✓ | ✓ | ✓ |
| Q-02 | ✓ | ✓ | ✓ |
| Q-03 | ✓ | ✓ | ✓ |
| Q-04 | ✓ | ✓ | ✓ |
| Q-05 | ✗ | ✗ | ✓ |
| Q-06 | ✓ | ✓ | ✓ |
| Q-07 | ✓ | ✓ | ✓ |
| Q-08 | ✓ | ✓ | ✓ |
| Q-09 | ✓ | ✓ | ✓ |
| Q-10 | ✓ | ✓ | ✓ |
| Q-11 | ✓ | ✓ | ✓ |
| Q-12 | ✓ | ✓ | ✓ |
| Q-13 | ✓ | ✓ | ✓ |
| Q-14 | ✗ | ✓ | ✓ |
| Q-15 | ✓ | ✗ | ✓ |
| Q-16 | ✓ | ✓ | ✓ |
| Q-17 | ✗ | ✗ | ✓ |
| Q-18 | ✓ | ✓ | ✓ |
| Q-19 | ✓ | ✓ | ✓ |
| Q-20 | ✗ | ✗ | ✓ |

---

## Part C — Explain and choose (Hard)

### C1 — Does the tool description matter?

I ran S3 again on five questions with the one-line description "Looks things up." and changed nothing else.

| Question | Calls (your description) | Calls (vague) | Answer (yours) | Answer (vague) |
|---|---:|---:|---|---|
| Q-01 | 7 | 5 | ossbridge, 4.6 | ossbridge, 4.6 |
| Q-05 | 7 | 5 | coldharbour, 14235 | coldharbour, 14235 |
| Q-09 | 7 | 7 | millbrook, 0.6 | millbrook, 0.6 |
| Q-14 | 7 | 7 | ashgrove, 4.9 | ashgrove, 4.9 |
| Q-20 | 10 | 10 | ashgrove, 2993 | ashgrove, 2993 |

With the vague description all five answers stayed correct (5 of 5). For the five questions together the run used 12,993 input tokens and 1,151 output tokens and took 31.5 seconds. Q-09 is the one I looked at in the log (`outputs/run1_vague/s3/Q-09.json`). The model made exactly the same 7 calls as with my description: the same four lookups, the same fields and the same three calculations, and it gave the same answer. The only differences were 3,045 input tokens instead of 3,477 (the shorter description is sent with every round) and 7.2 seconds instead of 5.5, which I think is just normal variation between runs. For the other questions the number of calls was the same on Q-14 (7) and Q-20 (10), and lower on Q-01 and Q-05 (5 instead of 7). I did not open those two logs, so I do not know why, but one possibility is that with the vague description the model put both divisions and the subtraction into fewer `calculate` calls. The answers were correct anyway. Why it still worked: the tool names, the parameter names (`district`, `field`, `expression`) and the list of allowed field names were still sent, and that already tells the model what the tools do. I did not test it, but I expect the description to matter for the rules that are written only in it: the tariff (`district='region'`) in Q-08 and Q-17, and the fact that archived profiles are ignored.

### C2 — Three mistakes explained

**S1, Q-05 (run 1).** The model got the district right (coldharbour) but the number wrong: 14344 instead of 14235. In its answer it writes "Stonecairn: 2,884.6 million ÷ 14,926 = 193,142 tenge per resident" and "Coldharbour: 2,366.9 million ÷ 11,407 = 207,486". The real values are about 193,260 and 207,495. So the Coldharbour division is almost right, but the Stonecairn one is off by about 120, and that goes straight into the answer. The model has no calculator here. It predicts the digits of a long division one after another, and nothing checks the result.

**S2, Q-05 (run 1).** S2 asked five times and still got it wrong. The five samples gave 14329, 14342, 14348, 14356 and 14323, and all five are too high. In the samples the Coldharbour division is close every time (207,486 to 207,514, real value about 207,495), but Stonecairn comes out between 193,149 and 193,168 every time, while the real value is about 193,260. So the model made the same kind of slip in every sample, always in the same direction. Voting only helps when the mistakes are random and the right answer is the most common one. Here the five answers were all different, so each got one vote, and when there is a tie my code keeps the first sample (`votes` in `outputs/run1/s2/Q-05.json`). So the vote did not really vote. Q-20 in run 1 went the same way (2999 instead of 2993).

**S3, the most expensive question.** S3 had no wrong answer, so I picked the question with the most tool calls: Q-11, with 10 calls in run 1 and 11 in run 2 (Q-20 also needed 10). The run 1 log (`outputs/run1/s3/Q-11.json`) shows 4 rounds. In round 1 there are six `lookup` calls (pupils and schools for Redfen, Ashgrove and Millbrook). In round 2 there are three divisions such as `3147 / 10`. In round 3 there is one subtraction, `370.8 - 314.7`, which returned 56.10000000000002, and round 4 is the answer `ANSWER: Redfen | 56.10`. It used 3,878 input tokens and 281 output tokens. Each round sends the whole conversation again (system prompt, question, every earlier tool call and every result), so the input grows round after round and the total is more than rounds times one call.

Why the calculator removes mistakes: the model only decides what to compute, for example `7146000 * 142.35 / 90212`, and the tool computes it exactly. The model cannot do that by itself, because its arithmetic is a guess made from patterns. This is why S3 got Q-05, Q-17 and Q-20 right in both runs, and S1 and S2 missed them at least once. It stops working when the model writes the wrong expression or asks for the wrong field. The tool would then return an exact number for the wrong question.

### C3 — Which strategy I would use, and what would change it

I would use S3. It was right on 20 of 20 questions in both runs, while S1 got 16 and 13 and S2 got 16 and 17. It used about 1.3 times the tokens of S1 (57,635 against 44,279 in run 1, 60,033 in run 2) and only about a quarter of the tokens of S2. The cost was about $0.017 per run, against $0.011 for S1 and $0.055 for S2. The time per question was about 4.7 to 4.9 seconds, against about 1.6 for S1 and 7.4 to 8.0 for S2.

I did not choose S1 because it is wrong exactly where the work is arithmetic or where the names are close. It missed four questions in run 1 and seven in run 2. It is cheapest and fastest, so it is a good choice only if the questions are easy.

I did not choose S2 because it costs five times as much as S1 (the documents are sent five times) and was no more reliable: 16 and 17 against 16 and 13. It also does not fix mistakes that are the same in every sample.

What would change my choice:

- 1,000 times more documents. S1 and S2 would not fit in the prompt at all, and each call would cost a fortune. S3 would still work if `lookup` searches an index and returns only a few short matches.
- Questions with no real arithmetic and a strict time limit, say under two seconds. S1 got Q-06, Q-10, Q-11, Q-12, Q-13, Q-16, Q-18 and Q-19 right in both runs, so for this kind of question S1 is enough and S3 is a slower way to get the same answer.
- Questions where one wrong number is very costly and the documents are small. Still S3, because the calculator makes the arithmetic exact.

### C4 — How sure I can be

The two runs differed by 3 questions for S1 (16 and 13), by 1 for S2 (16 and 17), and by 0 for S3 (20 and 20). S3 was ahead of S2 by 4 and 3 questions, which is about the same size as the swing of S1 between its own two runs. So I trust that S3 is better than S1 more than I trust that it is better than S2. The order S3 first is the same in both runs, but two runs is not many.

One question is 5 points of accuracy, so one lucky or unlucky answer moves the result a lot. My scoring is also generous. Some answers passed only because of the one-digit rule, for example S2 on Q-09 in run 1 (0.5 instead of 0.6) and S2 on Q-14 in both runs (4.8 instead of 4.9). With a strict rule S1 and S2 would look even worse. Another limit: my `lookup` is written for these 17 documents, so 20 of 20 may not carry over to a different corpus.

As a rough guess, to trust a gap of about 10 points I would want around 100 questions and several repeated runs. I did not test this, it is only the usual rule that the error of a percentage shrinks with the square root of the number of questions.

### Final questions

1. When the model sends a `tool_calls` message, nothing has run yet. It is only a request, written as text: a function name and its arguments. My code decides whether to run it, runs it, and sends the result back. The model never runs code itself.
2. `arguments` arrives as a string because the API returns text, and the model can write anything in it. If I pass the string straight into my function, Python sees one long string and not `district` and `field`, and broken JSON or missing keys can crash the program. So I use `json.loads`, check that the result is a dictionary, and send an error message back to the model if it is not.
3. The two tool definitions add 409 input tokens to every S3 request. I measured it by sending the same short message with and without the tools (`python run.py --measure-tools`, saved in `outputs/tool_definition_tokens.json`). Over a question with 3 or 4 rounds that is paid 3 or 4 times.
4. S2 cost 5.0 times more than S1 in run 1 ($0.0553 against $0.0110) and 5.1 times in run 2. The input tokens are 222,195 against 44,279. The reason is that S2 sends the same documents five times for every question. The output is about five times larger too (9,070 against 1,772 tokens), because it is five step by step answers and not one short one.
5. Q-11 needed the most tool calls (10 in run 1 and 11 in run 2), then Q-20 (10 in both runs) and Q-13 (9). No question needed more than 4 rounds and many tied at 4, so rounds alone do not tell them apart. In the Q-11 log (run 1) the model asked for all six facts in round 1 (pupils and schools of three districts), then for the three divisions in round 2, then for one subtraction in round 3, and answered in round 4. Three districts with two facts each, and a division for each, is why it needed so many calls, and asking for them in parallel is why it did not need many rounds.
6. With 100,000 documents I could not load everything into memory for each call or put it in a prompt. I would build an index once, for example a search index or a table of facts extracted in advance, and `lookup` would return only the top few short matches. The rules about archived profiles and corrections would stay in code, as filters, so the model does not have to choose.
7. `calculate` never uses `eval` or `exec`. It reads the expression with `ast` and walks only the nodes for numbers, `+ - * / **` and unary signs. Anything else (calls, attributes, names, strings) is refused. The length (200 characters), the exponent (at most 100) and the size of numbers (at most 1e18) are limited, so `9**9**9` cannot freeze it. The model can still misbehave in small ways: it can ask for a wrong formula, which the tool computes correctly, or keep asking forever, which is why the loop has a round limit.
8. Tools helped most on questions where the model had to divide or multiply long numbers: Q-05, Q-17 and Q-20. S1 and S2 missed each of them at least once, and S2 missed Q-05 and Q-17 in both runs, while S3 was right every time. Tools helped least on simple questions without hard arithmetic, like Q-10 (the age difference between two districts) or Q-06 (a sum of two populations). S1 got these right in both runs, faster and cheaper.
