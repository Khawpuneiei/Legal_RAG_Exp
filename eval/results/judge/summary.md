# LLM judge: reviewer note quality

Judge llama3.1:8b (generator family: qwen2.5), 18 test requests sampled with a fixed seed (20%), seed-1 runs, binary rubric, reasons before verdicts, condition names hidden. Score = share of the five questions answered true. Brackets: 95% bootstrap CIs over requests. Length bias: Spearman rho between note length (words) and score.

| Condition | judge score | q1_parties | q2_requests | q3_problems | q4_route | q5_no_invention | mean words | length rho |
|---|---|---|---|---|---|---|---|---|
| S0 | 0.37 [0.28, 0.44] | 0.00 | 0.06 | 0.61 | 0.44 | 0.72 | 10 | -0.27 |
| S1 | 0.41 [0.30, 0.52] | 0.28 | 0.00 | 0.61 | 0.72 | 0.44 | 14 | 0.11 |
| S2 | 0.34 [0.24, 0.43] | 0.17 | 0.06 | 0.61 | 0.61 | 0.28 | 25 | 0.35 |
| S3 | 0.30 [0.19, 0.42] | 0.11 | 0.00 | 0.67 | 0.44 | 0.28 | 12 | -0.05 |
| S4 | 0.37 [0.27, 0.47] | 0.06 | 0.00 | 0.67 | 0.61 | 0.50 | 10 | 0.06 |
| S5 | 0.27 [0.19, 0.33] | 0.06 | 0.00 | 0.56 | 0.44 | 0.28 | 16 | -0.13 |
| S0s | 0.30 [0.19, 0.41] | 0.06 | 0.11 | 0.56 | 0.39 | 0.39 | 11 | -0.23 |
| H-det | 0.38 [0.27, 0.50] | 0.44 | 0.00 | 0.56 | 0.56 | 0.33 | 15 | 0.02 |
| H0 | 0.41 [0.30, 0.52] | 0.28 | 0.06 | 0.61 | 0.61 | 0.50 | 25 | 0.02 |
| H1 | 0.37 [0.22, 0.51] | 0.28 | 0.06 | 0.56 | 0.56 | 0.39 | 24 | 0.13 |
| H2 | 0.39 [0.24, 0.53] | 0.33 | 0.11 | 0.56 | 0.50 | 0.44 | 14 | -0.33 |
| H3 | 0.38 [0.23, 0.52] | 0.33 | 0.11 | 0.56 | 0.50 | 0.39 | 15 | -0.33 |
| H4 | 0.38 [0.23, 0.52] | 0.33 | 0.11 | 0.56 | 0.50 | 0.39 | 15 | -0.33 |
| H3b | 0.47 [0.36, 0.58] | 0.50 | 0.06 | 0.67 | 0.61 | 0.50 | 15 | 0.00 |

Human spot-check: `human_spotcheck.csv` holds the same notes with the judge verdicts hidden behind blind ids. A team member fills the five human_* columns (1/0); then `python eval/judge.py --kappa eval/results/judge/human_spotcheck.csv` reports Cohen's kappa between judge and human (plan section 7). This step needs a person and has not been done.
