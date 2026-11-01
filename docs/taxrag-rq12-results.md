# TaxRAG RQ1 and RQ2: results

**Judged:** 1 November 2026 · **Protocol:** [`docs/taxrag-rq12-protocol.md`](taxrag-rq12-protocol.md) (written before any answer existed) · **Code:** `eval/tax_rq12.py`, `eval/tax_judge.py`, `src/tax/research.py` · **Raw outputs:** `eval/results/tax/*_rq12*` · **Answer model:** qwen3:8b as a local stand-in for his gpt-oss-120b, with his prompt, citation checker and 2,000-token cap (thinking included).

## Answer in short

- **RQ1, the skill: no gain.** The skill chosen on dev (S2, the focused skill) scores −0.025 against his prompt on the 79 test questions. On dev it had scored +0.062. The variants that load the whole skill answered more questions wrongly (exploratory, see below).
- **RQ2, a harness around his single call:**
  - **The validation retry (V)** is the only change that never lowered a question's score: +0.038, with 4 questions better and 0 worse. It is not significant: Wilcoxon p 0.125, Holm 0.375. 3 of the 4 rescues came from a reply that ran out at the 2,000-token cap with no text; the 4th came from a reply that cited no source. 2 of the 6 extra answers were wrong.
  - **Deep Tax Research as a fixed pipeline (DTR)** scores −0.025, also not significant. It is no better on dev either (−0.013).
- **Exploratory, not pre-registered:**
  - **The research agent plus the retry (DTRa+V) is the highest-scoring condition:** 0.823 against 0.747 on test, and tied highest on dev. It has the second-fewest wrong answers (3; DTRa has 2). Without the retry the agent is level with his setup (DTRa 0.753 against 0.747), and against the retry alone it is +0.038 (n.s.), half of its lead.
  - It was picked after seeing the data, out of 13 conditions. It is therefore a hypothesis to test on new questions, not a finding.

## Results

### Every condition (test, 79 answerable and 20 out-of-scope questions)

Correct (all): correct 1, partial 0.5, incorrect or unanswered 0, over the 79 answerable questions. Net: correct (all) minus the share answered wrongly, which counts a wrong answer as a cost rather than as 0. Calls, tokens and seconds are per question, from `generation_summary_rq12.md`.

| Condition | What it is | Answered | Correct / partial / incorrect | Correct (all) | Wrong | Net | Out-of-scope answered | Calls | Model tokens | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|
| `B0` | his deployed setup | 71/79 | 52 / 14 / 5 | 0.747 | 5 | 0.684 | 3/20 | 1.0 | 5,139 | 32 |
| `B1` | R6y in place of his expansion | 70/79 | 56 / 9 / 5 | 0.766 | 5 | 0.703 | 1/20 | 1.0 | 5,442 | 27 |
| `B0w` | his ranking with 4,000 tokens | 69/79 | 50 / 14 / 5 | 0.722 | 5 | 0.658 | 0/20 | 1.0 | 7,552 | 32 |
| `S1` | whole skill, system prompt | 76/79 | 50 / 12 / 14 | 0.709 | 14 | 0.532 | 2/20 | 1.0 | 10,106 | 38 |
| `S2` | focused skill (chosen on dev) | 75/79 | 49 / 16 / 10 | 0.722 | 10 | 0.595 | 1/20 | 2.0 | 7,495 | 36 |
| `S3` | whole skill, user message | 76/79 | 41 / 21 / 14 | 0.652 | 14 | 0.475 | 2/20 | 1.0 | 10,094 | 37 |
| `S4` | skill written by qwen3:8b | 71/79 | 43 / 21 / 7 | 0.677 | 7 | 0.589 | 0/20 | 1.0 | 5,498 | 32 |
| `V` | B0 + validation retry | 77/79 | 54 / 16 / 7 | 0.785 | 7 | 0.696 | 3/20 | 1.1 | 5,978 | 38 |
| `DTR` | Deep Tax Research, fixed pipeline | 71/79 | 49 / 16 / 6 | 0.722 | 6 | 0.646 | 1/20 | 3.0 | 10,297 | 47 |
| `DTR+V` | DTR + retry | 77/79 | 50 / 18 / 9 | 0.747 | 9 | 0.633 | 1/20 | 3.2 | 11,438 | 52 |
| `DTRa` | Deep Tax Research as an agent | 70/79 | 51 / 17 / 2 | 0.753 | 2 | 0.728 | 0/20 | 4.3 | 19,047 | 68 |
| `DTRa+V` | agent + retry | 77/79 | 56 / 18 / 3 | **0.823** | 3 | **0.785** | 0/20 | 4.4 | 20,166 | 74 |
| `C` | B1 + S2 + V (chosen on dev) | 79/79 | 54 / 14 / 11 | 0.772 | 11 | 0.633 | 2/20 | 2.1 | 8,534 | 29 |

Judging: 741 distinct answers, shown side by side and shuffled with the condition hidden. Two LLM judges (Claude agents) read each batch in opposite orders, and a third graded the 54 answers they did not settle: 43 disagreements and 11 answers only one of them graded. The first two agreed on 94% of the 730 answers both graded (Cohen's κ 0.88). No person checked the grades.

### Pre-registered comparisons (correct (all), test, paired over the 79 answerable questions)

Mean A − B [95% bootstrap CI], Wilcoxon p, and the number of questions where A scored higher / lower.

| | A − B | Wilcoxon p | Holm p | Higher / lower |
|---|---|---|---|---|
| **Primary** RQ1: `S2` − `B0` | −0.025 [−0.108, +0.057] | 0.622 | 1.000 | 9 / 14 |
| **Primary** RQ2, retry: `V` − `B0` | +0.038 [+0.006, +0.082] | 0.125 | 0.375 | 4 / 0 |
| **Primary** RQ2, research: `DTR` − `B0` | −0.025 [−0.120, +0.070] | 0.630 | 1.000 | 13 / 16 |
| `S1` − `B0` | −0.038 [−0.127, +0.051] | 0.442 | | 10 / 15 |
| `S3` − `B0` | −0.095 [−0.184, −0.013] | 0.041 | | 8 / 18 |
| `S4` − `B0` | −0.070 [−0.146, +0.006] | 0.102 | | 8 / 17 |
| `S2` − `S3` | +0.070 [−0.025, +0.165] | 0.155 | | 19 / 12 |
| `DTR` − `B1` | −0.044 [−0.127, +0.032] | 0.266 | | 8 / 13 |
| `DTRa` − `DTR` | +0.032 [−0.051, +0.114] | 0.434 | | 14 / 11 |
| `DTR+V` − `DTR` | +0.025 [+0.000, +0.063] | 0.250 | | 3 / 0 |
| `DTRa+V` − `DTRa` | +0.070 [+0.019, +0.133] | 0.031 | | 6 / 0 |
| `C` − `B0` | +0.025 [−0.051, +0.108] | 0.495 | | 11 / 9 |

- **None of the three primary comparisons is significant after Holm.**
- As pre-registered, the secondary comparisons are unadjusted. None would remain significant after correcting across the nine.
- **V's interval excludes 0, but we do not count V as a gain.** With only 4 questions different, a bootstrap resample contains none of them with probability (75/79)^79 = 0.017, so the lower bound is above 0 almost by construction. The exact test cannot go below p = 0.125 with 4 questions. Where the interval and the exact test disagree in these tables, trust the exact test.

### Exploratory comparisons (not pre-registered)

The share of answers that are wrong was not a pre-registered measure. Pooling dev with test is reported only for conditions that dev did not shape: the retry, DTR and DTRa. The skill was written from dev errors, so its dev scores are biased in its favour.

| | Test | Pooled dev + test (119 questions) |
|---|---|---|
| `DTRa+V` − `B0`, correct (all) | +0.076 [−0.006, +0.165], p 0.079, 19 / 11 | +0.071 [+0.004, +0.139], p 0.043, 27 / 16 |
| `DTRa+V` − `V`, correct (all) | +0.038 [−0.038, +0.120], p 0.335 | +0.029 [−0.034, +0.088], p 0.346 |
| `V` − `B0`, correct (all) | +0.038, 4 / 0 | +0.042 [+0.013, +0.076], p 0.016, 7 / 0 |
| `DTR` − `B0`, correct (all) | −0.025 | −0.021 [−0.101, +0.059], p 0.611 |
| Wrong answers, `DTRa` vs `DTR` | 2 vs 6 | questions wrong only under one: 1 vs 9, p 0.021 |
| Wrong answers, `DTRa+V` vs `DTR+V` | 3 vs 9 | questions wrong only under one: 1 vs 11, p 0.006 |
| Wrong answers, `S1` vs `B0` | 14 vs 5 (10 questions worse, 1 better, p 0.012) | – |

- None of these p-values survives a correction for the number of comparisons made.
- The test questions have now been used in several rounds. A test of DTRa+V therefore needs new questions, or at least his own model, and it should be compared against V as well as B0.

## Checks

- **A fresh blind re-grade agrees.** 240 answers decide the comparisons above: every answer where two compared conditions differ. New judges re-graded them blind, at a higher effort level. They agreed with the original grades on 93%. The disagreements were 8 partial-to-correct, 7 correct-to-partial and 2 incorrect-to-partial. No conclusion changes:
  - `V` − `B0`: +0.032, 4 / 0;
  - `DTR` − `B0`: −0.025;
  - `DTRa+V` − `B0`: +0.070;
  - `S3` − `B0`: −0.101;
  - wrong answers, `DTRa+V` vs `DTR+V`: 0 vs 6.
- **Reproducibility check (pre-registered).** B0 in this round scored +0.019 against B0 in the earlier qwen3:8b round (9 questions better, 7 worse). That round ran on a different server layout and was judged in a different round. Generation is deterministic here: temperature 0, seed 0, cached calls. So the 16 changed grades out of 79 measure how sensitive answers are to small changes, plus judge noise.
  - **Consequence:** any change to the prompt or the context re-draws about a fifth of the answers. Differences up to about ±0.06 between such conditions are within that churn.
  - **Why the retry comparisons are cleaner:** a retry condition makes the same first call as its base, so it can differ only where a retry fires. That is why the retry's 4 / 0, 3 / 0 and 6 / 0 patterns stand out.
- **The PR's code matches what was evaluated.**
  - **Deep Tax Research:** PR #6's version (`rag/research.py`) follows the evaluated DTR step for step. Its A\* matches the evaluated R6y on all 447 recorded source lists.
  - **The retry:** PR #6's `retries` option reproduces V when it is set to 2.
  - **Helper calls differ:** the evaluation made them with thinking off, in JSON mode, with a 400-token cap. The PR makes them through gpt-oss-120b with medium reasoning and his 2,000-token cap.

## Why

- **The retry** rescues replies that ran out of tokens.
  - On test it retried 8 of B0's refusals, 7 of which were empty replies at the cap. 2 became correct, 2 partial and 2 incorrect, and 2 stayed refused.
  - On the research agent's prompts, it turned 5 of 7 refusals into correct answers. That gap reverses on dev.
  - Its value in his app depends on how often gpt-oss-120b runs out at the cap, which has not been measured.
- **DTR displaces his best hits.**
  - The planner always issued the maximum 3 queries and the gap check always 2, on every test and dev question.
  - Against those five sub-queries, the question's double weight in the merge is not enough: DTR keeps 69% of his hits.
  - On test its context held slightly more gold (0.928 against 0.918), but the answers were no better. On dev it held less (0.854 against 0.917).
- **The research agent stays close to B1.**
  - It made one search in 83 of the 99 test questions, never more than two, then usually followed references once.
  - It keeps 82% of his hits. It answers from B1's exact sources when it stops at once (9 test questions).
  - Its extra sources rarely contain new gold: 3 of 71 test questions.
  - **Why it has fewer wrong answers than DTR:** it keeps B1's refusals. On the 9 test questions B1 refuses, DTR answers 4 wrongly, while the agent still refuses 7.
  - **Where DTRa+V's lead comes from:** along B0 → B1 → DTRa → DTRa+V, the steps are +1.5, −1.0 and +5.5 points. The retry provides the lead, not the agent's research.
- **The skill misdirects qwen3:8b.**
  - In 9 of 17 cases where a skill condition was wrong and B0 right or partial, a module's checklist pulled in the wrong rule. Examples: a structural-works exclusion in a capital-allowance question; commencement rules in a question about when costs are deductible.
  - The other 8 were misreadings of the facts.
  - It also pushes the model to answer where B0 gave no answer. Across S1 to S3, 11 such answers were wrong. On 4 of them the gold source had not been retrieved, so refusing was right.
  - Its gain on dev came from the dev questions its error notes were written from, mostly by re-running B0's cap failures. The skill qwen3:8b wrote for itself, without those notes, gained as much on them.

## What this means for his repo

- **Deep Tax Research (the fixed pipeline in PR #6) is not justified.** It is no better on either split, and it makes 3 calls per question. Remove it, with its app toggle.
- **The retry stays an option, off by default.** It never lowered a question's score, but its gain is 4 questions in 79 and not significant, and a third of its rescues were wrong. Before turning it on, run his deployed setup once over the test questions on gpt-oss-120b, count replies that stop at the cap, and compare with simply raising the cap. Neither was tested.
- **R6y stays optional, with no measured gain on answers.** `B1` − `B0` is +0.019, the same size as the difference between the two B0 runs.
- **Don't add the skill.** For qwen3:8b it did not help, and in an exploratory count the whole-skill variants answered more questions wrongly. It was not tried on gpt-oss-120b.
- **The research agent with the retry is a candidate for a follow-up, not for this PR.**
  - The test would need new questions, a comparison against V, and gpt-oss-120b.
  - Porting it needs the agent loop and prompt, a `present` argument on `DependencyGraph.expand`, tests and app changes.
  - With gpt-oss-120b on Groq, three risks: JSON replies without JSON mode, reasoning tokens in every step, and about 4 calls and 19,000 tokens per question against the free tier's per-minute limit.

## Not yet known

- How often gpt-oss-120b hits the 2,000-token cap in his app, and whether a higher cap does what the retry does.
- Whether any of this holds with gpt-oss-120b, his app's model.
- Whether the effects concentrate in one topic area; no per-area breakdown was computed.
- Whether a person would agree with the LLM judges on the decisive answers.
