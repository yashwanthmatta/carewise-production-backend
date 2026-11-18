# Help chat safety evaluations

## Automated, on every PR (backend CI, no network, synthetic data)

- **`tests/api/test_assistant.py`:**
  - the system prompt carries the medicine rule and the emergency rule;
  - dosing-like replies are withheld;
  - the report summary is shared only when the person chose to share it;
  - Spanish replies are covered.
- **`tests/api/test_assistant_reliability.py`:**
  - each provider failure is named in the log;
  - the message shown to people is calm;
  - the question and key are never logged;
  - the timeout and retries are set;
  - the status check works and is cached;
  - pending medicine entries never reach the model;
  - verified entries come with their source;
  - names are matched as whole words;
  - an entry marked verified without sources is refused.
- **Frontend `scripts/eval/ai-guide.mjs`:**
  - emergency words are answered before any network call;
  - the offline message is calm, with no internal details.

## Before any live use of answers about medicines

- **Real-model run:** run `scripts/assistant_eval/run.py` against the real model. All "forbid: dose_advice" items must pass, and the made-up brand must not be identified.
- **Clinical review:** a qualified clinician reviews a sample of real-model answers. It has not been done. No answer is ever labelled clinician-reviewed.

## Rules that automated learning may never change

- urgency rules;
- lab-range interpretation;
- the dosing guard;
- the emergency answer;
- the medicine rule.

Changes to these need the owner and an independent clinical review.
