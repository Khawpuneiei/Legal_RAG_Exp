# TaxRAG on Claude, a public tax benchmark, and IRAS's chatbot

**7 November 2026.** Three questions, two about the teammate's Singapore income-tax RAG ([Saiharshaa/SGtax-rag](https://github.com/Saiharshaa/SGtax-rag)) and one about Claude Opus 5.5 by itself:

1. How good is his pipeline with Claude (Claude Opus 5.5, through the Anthropic API) as its answer model, in place of the local
   stand-ins of the earlier rounds? (His app itself runs gpt-oss-120b on Groq, which has still not been tested.)
2. How does Claude do on a public tax benchmark with a published leaderboard?
3. How do the existing Singapore government tax chatbots, and published results for other tax chatbots, compare?

Earlier rounds: [retrieval methods](taxrag-results.md), [skills and harnesses (RQ1/RQ2)](taxrag-rq12-results.md).

## Short answer

- **His pipeline with Claude scores 0.937 correct (all) on the 79 held-out test questions** (71 correct, 6 partial, 1 wrong,
  1 declined; 0.899 fully correct) and declines all 20 questions his corpus cannot answer. The local qwen3:8b stand-in of the
  earlier rounds scores 0.715 on the same questions in the same blind judging (+0.222 [+0.139, +0.304], 31 questions better,
  3 worse).
- **Without his retrieval, Claude does much worse:** 0.589, with 19 of the 79 answered wrongly against 1 (+0.348 [+0.247,
  +0.456]). On these questions, removing retrieval (with his prompt and refusal rule) costs Claude more than replacing Claude
  with qwen3:8b; qwen3:8b with retrieval against Claude without is +0.127 [+0.006, +0.253] (Wilcoxon p = 0.08).
- **Against IRAS's own chatbot** (25 sampled questions, asked once each on 7 November 2026): his pipeline with Claude 0.920,
  the IRAS Bot 0.520 (+0.400 [+0.180, +0.620]). The gap is coverage: the IRAS Bot answered 15 of the 25 and asked for a
  shorter question on the other 10; on the 15 it answered it scores 0.867, and Claude in his pipeline 0.900.
- **TaxCalcBench** (Column Tax's public US tax-return benchmark, TY 2024, 51 returns), Claude Opus 5.5 alone, no retrieval:
  64.71% of returns fully right at the benchmark's default effort and 66.67% one level up, above the best published TY24 row
  (62.75%) but within each run's uncertainty (95% interval 51% to 76% at the default, 53% to 78% one level up); at the same
  level the published runs are 58.82% (GPT-5.4 Pro) and 52.94% (Claude Opus 4.6). The TY24 board stops at models of early
  2026. No public Singapore tax benchmark with answers exists.
- **Deep Tax Search** (his PR #6 toggle) makes no measurable difference with Claude either: 0.949 against 0.943.
- **Cost:** $4.65 for 127 answers through his pipeline at list prices ($0.037 an answer), 8 s median; no reply in his
  pipeline came near his app's 2,000-token cap (largest 1,489 output tokens). This whole round cost $24.34 of API use.

## Setup

**Claude.** `src/llm/claude.py`: Claude Opus 5.5 (`claude-opus-5-5`) through the Anthropic Python SDK, behind his `ChatModel`
protocol (`rag.llm`: `complete(system, user)`), so it slots into his `rag.generate` unchanged. Effort `medium` (the model's
default, set explicitly; Opus 5.5 always thinks), up to 16,000 output tokens, Anthropic's server-side fallback on a safety
decline (never triggered: every reply ended normally and came from Opus 5.5). Every reply is cached with its token usage.
`eval/tax_generation.py --model claude` runs it.

**His pipeline.** `teammate-improved@gemini`: his deployed `improved` retrieval on his Gemini index (2,500 tokens of hits plus up
to 3 cross-referenced sections), his system prompt, numbered sources, citation rewriting, and his rule that an answer citing no
source becomes the refusal. The same condition is B0 in [RQ1/RQ2](taxrag-rq12-results.md).

**Questions.** The held-out test split: 79 answerable questions with gold sections and paragraphs (59 natural, 16 citing a
section, 4 citing a former section number) and 20 that the corpus cannot answer. They were written from his corpus and audited
by LLM agents before this round ([how](taxrag-results.md)), not by tax professionals or users. Plus his own 28 (25 answerable).

**Claude without retrieval** (`eval/tax_chatbots.py closed-book`): the question alone, with a short system prompt (answer
Singapore income-tax questions for tax associates, cite the ITA or IRAS guidance, say so if unsure). This changes the prompt
and drops his refusal rule as well as the retrieval: it is what a general assistant knows by itself.

**Existing chatbots.** A research sweep for this round (public tax benchmarks; government and company tax chatbots; most claims
then checked by a second agent) found one free, public, no-login Singapore tax chatbot: the **IRAS Bot** ("Chat with IRAS",
on every iras.gov.sg page), on GovTech's VICA platform. Its window said "This chatbot uses Gen AI" on 7 November 2026; IRAS
reports 1.7 million chatbot sessions in FY2025 and has published no accuracy figure.
- GovTech's SmartAnswer (GenAI answers in site search) is switched off on iras.gov.sg.
- **chat.gov.sg**, the whole-of-government GenAI assistant, was asked the same questions and its answers were judged in the
  same pool, although the research notes had already flagged that its terms of use (cl. 3.3(g)) forbid benchmarking the
  service; that flag was missed at the time. Its results are left out of this report and the repository.
- The Singapore company tools found are not comparable or not open: aitax.sg computes Form C-S drafts (no chat), iTaxQuest is
  behind a demo request, and the "SG TAX Agent" custom GPT runs inside ChatGPT (probably needing an account; the listing does
  not say).

The IRAS Bot got a seeded sample of 25 of the 79 answerable questions (by type: 19 natural, 5 section, 1 former number; seed
3415, `eval/results/tax/chatbot_sample.json`), typed into its public chat window on 7 November 2026: one question per fresh
conversation, asked once, as written. Its "please rephrase" fallback counts as no answer, like a refusal. Its replies are kept
in `.cache/tax/chatbots/`, outside the repository: the IRAS website terms bar republishing its content. No terms specific to the
IRAS Bot or to VICA could be found.

**Judging.** As in RQ1/RQ2: each question's answers from all systems, labelled A, B, ... in a seeded random order, system hidden,
graded correct / partial / incorrect against the gold sections by two LLM judges (Claude agents) reading in opposite orders, a
third on each disagreement. 243 distinct answers; the first two judges agreed on 95% (Cohen's κ 0.91). "Correct (all)" counts
partial as half and no answer as 0, over every question. Then a separate skeptical re-grade of the 25-question sample (below).

## Results

### His pipeline with Claude, all 79 answerable test questions

| System | Answered | Correct / partial / incorrect | Correct (all) | Fully correct | Wrong |
|---|---|---|---|---|---|
| **Claude Opus 5.5 in his pipeline** | 78 | 71 / 6 / 1 | **0.937** | 0.899 | 0.013 |
| qwen3:8b in his pipeline (earlier stand-in) | 71 | 47 / 19 / 5 | 0.715 | 0.595 | 0.063 |
| Claude Opus 5.5 without retrieval | 79 | 33 / 27 / 19 | 0.589 | 0.418 | 0.241 |

Paired over the 79 questions (95% bootstrap CI, Wilcoxon p):
- Claude in his pipeline − qwen3:8b in his pipeline: **+0.222 [+0.139, +0.304]**, p < 0.001, 31 questions better, 3 worse.
- Claude in his pipeline − Claude without retrieval: **+0.348 [+0.247, +0.456]**, p < 0.001, 45 better, 6 worse; wrong answers
  1 against 19 (−0.228 [−0.329, −0.127]).
- qwen3:8b in his pipeline − Claude without retrieval: +0.127 [+0.006, +0.253], p = 0.08, 34 better, 16 worse.

By type, Claude in his pipeline scores 0.949 on the 59 natural questions, 0.938 on the 16 citing a section and 0.750 on the 4
citing a former section number.

qwen3:8b scored 0.747 on the same answers in the RQ1/RQ2 judging and 0.715 here: the two judging rounds differ by about 0.03.

**Retrieval and citations** (his metrics, no judging; qwen3:8b figures are for the same answers, RQ1/RQ2 B0): Claude answered
78 of 79 and declined all 20 out-of-scope questions; qwen3:8b answered 71 and declined 17. Claude cites more of the gold
sections and paragraphs (gold cited, all: 0.878 against 0.776) at a lower citation precision (0.472 against 0.569), because it
cites more of the sources it is given. Those sources held 92% of the gold units, so retrieval sets most of the remaining
ceiling. qwen3:8b ran out of its 2,000-token budget on 8 test answers; Claude's largest reply was 1,489 tokens. On his 28
questions: 25 of 25 answered, 3 of 3 out-of-scope declined.

**Its one wrong answer** (h021) is a retrieval miss, not a reasoning error: the question applies s 37B(17), which works through
s 37A(4); his `improved` retrieval returned s 37B(17) but not s 37A(4), and Claude, told to answer only from the sources, said
it could not compute the figure. Claude without retrieval, and the IRAS Bot, both gave the right $100,000. Following the
sections a hit depends on is what Deep Tax Search (A\* expansion, his PR #6 toggle, `R6y@gemini`) does, so Claude was run
with it on as well ($4.63 more) and judged blind against the run without it in a separate pool of the same design (155 distinct
answers, agreement 97%):

| Claude Opus 5.5 in his pipeline | Answered | Correct / partial / incorrect | Correct (all) | Gold cited (all) |
|---|---|---|---|---|
| with Deep Tax Search | 79 | 73 / 4 / 2 | 0.949 | 0.907 |
| without (his setup today) | 78 | 72 / 5 / 1 | 0.943 | 0.878 |

No measurable difference on correctness (+0.006 [−0.019, +0.038]) or on the cited gold units (+0.030 [−0.000, +0.065], 5
better, 1 worse). It turned one refusal into a correct answer (h143) and one partial answer into a wrong one (h133), and it did
not fix h021: both contexts have s 37A(5) but not s 37A(4), and A\* added only other s 37 and s 37B subsections. The run without it scores 0.943 in this pool and 0.937 in the main one.

### Against the IRAS Bot, 25 sampled questions

| System | Answered | Correct / partial / incorrect | Correct (all) | Score on its own answered questions |
|---|---|---|---|---|
| **Claude Opus 5.5 in his pipeline** | 25 | 22 / 2 / 1 | **0.920** | 0.920 |
| qwen3:8b in his pipeline | 23 | 14 / 7 / 2 | 0.700 | 0.761 |
| Claude Opus 5.5 without retrieval | 25 | 11 / 9 / 5 | 0.620 | 0.620 |
| IRAS Bot | 15 | 12 / 2 / 1 | 0.520 | 0.867 |

Claude in his pipeline − IRAS Bot: **+0.400 [+0.180, +0.620]**, p = 0.005, 13 questions better, 2 worse; wrong answers level
(1 each).

- **When the IRAS Bot answers, it is mostly right.** On the 15 questions it answered: Claude in his pipeline 0.900, the IRAS
  Bot 0.867, Claude without retrieval 0.733, qwen3:8b 0.567.
- **The gap is coverage.** On the other 10 it gave its fallback, which asks for a single short message of at most 15 words.
  These are questions for tax associates, one to four sentences (mostly two) and 23 to 58 words each, most with amounts or
  dates: not what it is built for.
- It cites IRAS pages and e-Tax Guides ("View sources"); his pipeline cites the ITA and e-Tax Guide paragraphs.

**Skeptical re-grade** (`tax_chatbots.py regrade-score`). Two fresh judges re-graded the sample's 88 distinct answers blind,
told that some systems are better than others and not to assume any answer is right, to list every claim and recompute every
figure (agreement 91%, κ 0.82; the lower grade where they differ). It changed 8 of the 100 system-question grades, 6 of them
for Claude without retrieval, which fell to 0.500; every change was a downgrade. Claude in his pipeline 0.900, qwen3:8b 0.680,
IRAS Bot 0.520 (unchanged); Claude in his pipeline − IRAS Bot +0.380 [+0.140, +0.600], and every other gap on the sample still
excludes 0. That the re-grade cut Claude without retrieval most suggests the first judges were generous to its fluent but
unsourced answers.

**Out-of-scope check (10 November 2026,
[`eval/results/tax/chatbot_out_of_scope_summary.md`](../eval/results/tax/chatbot_out_of_scope_summary.md)).** The IRAS Bot was
asked 14 of the 20 out-of-scope test questions, the ones outside IRAS's remit. The other 6, on GST and stamp duty, are IRAS's
own subject. Same method as above, except the chat window now asks for a topic first, so "Corporate Income Tax" was used.
- **The IRAS Bot declined 3,** pointing them to ACRA.
- **It asked for a shorter question on 8.** All 14 are over its 15-word guidance, so this is not a clear refusal.
- **It answered 3 Singapore CPF or Companies Act questions,** citing IRAS pages. These were not graded.
- **It answered none of the 5 foreign-tax questions.**

His pipeline with Claude declined all 14.

## A public benchmark: TaxCalcBench (US federal returns)

No public Singapore tax benchmark with answers exists: the ACCA TX-SGP and ISCA/ACRA taxation papers are copyrighted and
their solutions are not public, and GovTech's PolicyBench (Singapore policy questions) has no tax domain. Of the public tax
benchmarks found, [TaxCalcBench](https://github.com/column-tax/tax-calc-bench) (Column Tax, MIT licence;
[paper](https://arxiv.org/abs/2507.16126), July 2025) is the one with open data, an objective score and a maintained
leaderboard: the model gets a taxpayer's data and returns a completed Form 1040, scored on 19 lines against expected returns
that Column Tax's tax analysts prepared (in the IRS MeF XML format). This tests Claude alone, with no retrieval and no Singapore
corpus. Its TY 2024 set (51 federal returns, JSON input) has no Claude Opus 5.5 row, so `eval/tax_calcbench.py` ran it, with
the benchmark's own prompt, data and evaluator imported unchanged, one run per return, no web search, no fallback.

Its TY24 path sends the thinking level as the effort, so its default level is effort `high`; `xhigh` is one level up.

| Model | Correct returns (strict) | Correct returns (within $5) | Correct (by line) | Correct (by line, within $5) |
|---|---|---|---|---|
| **Claude Opus 5.5, effort high (the TY24 default), this run** | **64.71%** (33 of 51) | **80.39%** (41) | **91.02%** | 93.81% |
| **Claude Opus 5.5, effort xhigh, this run** | **66.67%** (34 of 51) | 78.43% (40) | 91.85% | 93.91% |
| GPT-5.4 Pro (published) | 62.75% | 72.55% | 89.99% | 93.40% |
| GPT-5.4 (published) | 62.75% | 66.67% | 89.78% | 91.12% |
| Claude Opus 4.6 (published) | 52.94% | 64.71% | 87.00% | 89.16% |
| Gemini 3.1 Pro (published) | 49.02% | 68.63% | 88.54% | 92.16% |
| Gemini 3 Pro (published) | 36.27% | 73.53% | 85.42% | 93.83% |
| GPT-5 (published) | 31.86% | 54.41% | 81.45% | 86.09% |

The published rows are 6 of the 19 on the TY24 leaderboard and include the best published value in every column (62.75%,
73.53%, 89.99%, 93.83%). Each column takes the model's best of its 3 to 5 thinking levels, which favours the published rows;
GPT-5.4 Pro, GPT-5.4, Claude Opus 4.6 and Gemini 3.1 Pro are single runs, Gemini 3 Pro and GPT-5 means of 4.

- **Above every published TY24 row on fully correct returns, but not clearly.** The two runs agree on 48 of the 51 returns
  (32 right in both) and average 65.69%; each run's 95% interval (51% to 76% for 33 of 51, 53% to 78% for 34) includes the
  best published 62.75%. At the same level, "high", the leaderboard's single runs score 58.82% (GPT-5.4 Pro), 56.86%
  (GPT-5.4) and 52.94% (Claude Opus 4.6), against this run's 64.71%. On the by-line score within $5, Gemini 3 Pro's published
  93.83% is level with this run's 93.81% to 93.91%.
- **Not like for like.** The TY24 leaderboard stops at models of early 2026 (newest GPT-5.4, March 2026); none of the newer
  models that lead the maintained TY25 board was run on TY24. The answer keys have been public in the repository since July
  2025, so a model trained since may have seen them; Opus 5.5 is the most recent model here. On the current TY25 set (realistic
  PDFs, state returns), Column Tax's own board puts Opus 5.5 at 42% without web search, tied second (with Claude Fable 5.1)
  behind GPT-6 Astra's 44%, and at 70% with web search, tied fourth behind Meta Muse Wonder's 77.55% (over 49 of 50 returns).
- Lines most often wrong at effort high: line 16 (tax, 11 returns), line 24 (total tax, 10) and line 37 (amount owed, 9).
  Cost at list prices $5.41 at high ($0.11 a return, 28 s) and $7.17 at xhigh ($0.14, 44 s).

## Published results for other tax chatbots

No accuracy figure is published for the IRAS Bot. What exists elsewhere (each row checked against its source by a second agent;
self-reported figures marked):

| System | Who measured | Result |
|---|---|---|
| CRA "Charlie" chatbot (Canada) | Auditor General of Canada, October 2025 | Accurate on 2 of 6 tax questions; public AI tools 5 of 6 |
| TurboTax Intuit Assist, H&R Block AI Tax Assist (US) | Washington Post, March 2024, 16 questions (paywalled) | IRS Taxpayer Advocate summary: inaccurate or irrelevant up to 50% of the time; secondary reports: TurboTax wrong on more than half, H&R Block on 30% |
| IRS chat applications (US, rule-based) | TIGTA, June 2026 | 29 responses across 206 scripted flows could be improved (14%); 44 of 53 keywords not recognised or answered insufficiently |
| GOV.UK Chat, incl. HMRC guidance (UK) | Government, self-reported, 2026 | Accuracy 76% rising to 90% across all topics in pilots; graded by subject-matter experts and automated tools; question set unpublished |
| Claude Opus 5.5 on Vals AI Tax Agent Bench (US, private, 193 questions, tools) | Vals AI, 5 November 2026 | 45.57%, 4th; best 51.78% (Gemini 4 Carbon) |
| Claude Opus 5.5 on TaxCalcBench TY25 (US, 50 returns from PDFs) | Column Tax leaderboard | 42% fully correct returns without web search, 70% with |

## Caveats

- **The judges are LLMs, and Claude models.** Two of the four systems in the main pool are Claude (three of five counting the
  Deep Tax Search pool), and the questions were also written by LLM agents. The judging is blind and anchored on the gold
  sections, but an answer's style can give its system away, the skeptical re-grade suggests the first judges were generous to
  Claude without retrieval, and no person or non-Claude judge has checked the grades.
- **His pipeline has a home advantage.** The questions were written from the IRAS e-Tax Guides and the ITA that are in his
  corpus, and the judges see the gold units in the same form his pipeline cites them; the IRAS Bot retrieves from iras.gov.sg
  pages that may not contain the same paragraphs.
- **The IRAS Bot was asked questions it is not designed for.** It asks for questions of at most 15 words; these are scenario
  questions for tax professionals. A short FAQ-style set would measure it differently. One try per question, no rephrasing; the
  bot may change.
- **25 questions** for the bot comparison: wide intervals, though the gap to the IRAS Bot excludes 0 on both gradings.
- **Claude's cap:** 16,000 output tokens against his app's 2,000. No reply in his pipeline used more than 1,489, so the cap did
  not matter there; without retrieval, 4 of the 79 replies went past 2,000 tokens (largest 2,177), which his cap would cut.

## Reproducing

```
python eval/tax_generation.py --model claude --rpm 40 --configs teammate-improved@gemini R6y@gemini   # needs ANTHROPIC_API_KEY
python eval/tax_chatbots.py sample        # the fixed 25-question sample (already in eval/results/tax/)
python eval/tax_chatbots.py closed-book --all
python eval/tax_chatbots.py prep 8 claude-rag claude-closed qwen3-rag iras-bot chat-gov-sg --all   # the original pool; do not collect chat.gov.sg again
python eval/tax_chatbots.py score --exclude chat-gov-sg          # after the judges' verdicts are in .cache/tax/judge_chatbots/
python eval/tax_chatbots.py regrade-prep; python eval/tax_chatbots.py regrade-score --exclude chat-gov-sg
python eval/tax_chatbots.py prep 4 claude-dts claude-rag --all --set dts; python eval/tax_chatbots.py score --set dts
python eval/tax_calcbench.py run --effort high; python eval/tax_calcbench.py run --effort xhigh   # needs a clone in ../benchmarks/tax-calc-bench
```

The judges' verdicts come from LLM-agent batches as in [RQ1/RQ2](taxrag-rq12-results.md). The IRAS Bot's replies were entered
into its public chat window through a browser by an agent, one question at a time, and cannot be regenerated.
