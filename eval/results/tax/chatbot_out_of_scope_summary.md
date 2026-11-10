# IRAS Bot on out-of-scope questions (10 November 2026)

Does the IRAS Bot decline questions it has no basis to answer? The 20 out-of-scope test questions in
`data/tax/questions_heldout.jsonl` are outside the RAG's corpus (the Income Tax Act and five e-Tax guides). Not all of them
are outside IRAS's remit, so this test uses only the 14 that are.

- **Left out (IRAS's own subject, 6):** GST (h026, h057) and stamp duty (h027, h085, h114, h147). IRAS administers both,
  so for the IRAS Bot the right behaviour there is to answer.
- **Asked (outside IRAS's remit, 14):**
  - Malaysian, UK or Hong Kong tax (5);
  - the Companies Act or ACRA (4);
  - CPF (2);
  - hotel licensing, building control and accounting standards (1 each).

**Method:** the same as the 25-question sample of 7 November.
- Each question was typed into the public "Chat with IRAS" window on iras.gov.sg as written, once, in a fresh
  conversation.
- One thing changed: the window now asks for a topic before it shows the question box, so every question was asked
  under "Corporate Income Tax".
- The replies are kept in `.cache/tax/chatbots/iras-bot-oos.jsonl`, outside the repository.
- Each reply falls into one of three groups, recognised by the bot's fixed wording. No judging was needed.

| Reply | Count (of 14) | Questions |
|---|---|---|
| Declined and sent to the right agency (ACRA) | 3 | h059, h087, h144 |
| Asked for a shorter question (at most 15 words), no answer | 8 | h025, h056, h088, h115, h116, h118, h145, h149 |
| Answered, citing IRAS sources | 3 | h028 (Companies Act audit exemption), h060 (self-employed MediSave), h089 (CPF payment date) |

- **It declined 3 of 14.** All 3 are ACRA questions, and each reply points to ACRA. The 3 answers are on Singapore
  topics that IRAS pages cover, and each cites IRAS sources. They were not graded: there are no gold answers for
  out-of-scope questions.
- **It never answered a foreign-tax question.** All 5 (Malaysia, UK, Hong Kong) got the fallback.
- **The fallback can't be read as a refusal.** All 14 questions are 18 to 30 words, over the bot's 15-word guidance. It
  is the same fallback that met 10 of the 25 answerable questions on 7 November.
- **The RAG pipeline with Claude Opus 5.5 declined all 20 out-of-scope test questions**, these 14 included
  (`generation_per_question_claude.jsonl`, `docs/taxrag-claude-results.md`).
