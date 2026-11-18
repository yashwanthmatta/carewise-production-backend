# Model benchmarks

**No benchmark has been run.** The production key is rejected (E-001), and this build environment has no Anthropic key. No model comparison results exist yet. None are claimed.

## Ready to run

- **Questions:** `scripts/assistant_eval/questions.json` has 17 synthetic questions:
  - medicines: Dolo 650, a typo, the paracetamol/acetaminophen synonym, a dose question, an interaction question, a made-up brand, Crocin;
  - lab terms: LDL, A1C, TSH, eGFR;
  - an emergency;
  - Spanish;
  - questions about using the app;
  - an unclear question;
  - a non-medical question.
- **Runner:** `scripts/assistant_eval/run.py --models <ids> --approved-budget-usd <n>`.
  - It uses the production prompt, the reference context and the dosing guard.
  - It scores each answer against `expect` and `forbid`.
  - It reports median and p95 latency and stops at the budget.
- **Candidates:** the current model (`claude-opus-5-5`) against `claude-sonnet-5-5`, which is faster and costs less. Both are Anthropic models, so there is no new data processor.

## Owner decision needed

- **Approve a budget:** a full run of 17 questions on 2 models is expected to cost a few US dollars, at most.
- **Where it runs:** a run needs a key in an environment Claude can use. Either:
  - start a session in the "FollowThrough Health" environment, after adding the key there as a network secret; or
  - run the script yourself.

The production model changes only after real results and the owner's go-ahead.
