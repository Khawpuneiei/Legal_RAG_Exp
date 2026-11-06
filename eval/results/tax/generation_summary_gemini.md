# TaxRAG answers (gemini-3.8-flash, the teammate's prompt and citation checker)

Citation precision: share of an answer's citations that point at a gold unit (his metric). Gold cited: share of the question's gold units the answer cites, over answered answerable questions. Gold cited (all): the same over every answerable question, a refusal counting as 0, so a configuration cannot score higher by answering less.

## Teammate's 28 questions

| Configuration | Answerable answered | Out-of-scope refused | Citation precision | Gold cited | Gold cited (all) | Model calls | Source tokens |
|---|---|---|---|---|---|---|---|
| `teammate-improved@gemini` | 15/16 | 0/0 | 0.500 | 0.878 | 0.823 | 16/16 | 2871 |

