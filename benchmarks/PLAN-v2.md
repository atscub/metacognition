# KYL Metacognition Benchmark v2 — Implementation Plan

## Handoff Context

### What was done (v1)

Built and ran a 53-task benchmark (40 original + 10 theory-designed bias + 3 observed-failure) testing whether KYL metacognition skills improve AI reasoning. Ran across 2 models (Sonnet 4.6, Haiku 4.5) × 2 conditions (baseline, KYL). ~500+ sessions total.

**v1 finding**: KYL reliably improves epistemic process metrics (assumption acknowledgment +0.8, alternatives +0.9, confidence calibration +0.7) but does NOT improve error detection or final correctness. Effect sizes are large (r = 0.58–0.88) on process, near zero on outcomes.

**v1 problems identified**:
1. **Cognition and metacognition are conflated.** The scoring rubric measures both — correctness and process on the same 0-3 scale. A model that's simply smarter trivially looks more metacognitive.
2. **Self-evaluation confound.** AI-designed tasks test biases the AI already knows how to avoid. Theory-derived traps (bias-01 through bias-10) were resisted by both models in both conditions.
3. **No tool grounding.** KYL skills mandate "verify with tools" but `claude -p` sessions have no codebase to read and no web search happened (0 across all runs).
4. **Single-turn only.** The task runner can't test multi-turn dynamics (challenge-and-fold sycophancy, strategy switching under feedback).
5. **Observed-failure tasks are more valid.** Tasks derived from real AI failures during the project (bias-11 through bias-15) showed differentiated KYL effects — including one case where KYL made Haiku *worse* (justified avoidance via the socratic checklist).

### What's changing (v2)

v2 decouples metacognition from cognition, uses established academic frameworks, and measures metacognitive ability directly rather than as a side effect of task performance.

---

## Literature Foundation

v2 is grounded in three frameworks from the research literature:

### 1. DMC — Decoupling Metacognition from Cognition (Wang et al., AAAI 2025)

Core insight: metacognitive ability must be measured independently of cognitive ability. A model that gets everything right trivially "knows what it knows." DMC measures metacognition through **failure prediction** — can the model predict which questions it will get wrong?

**How we apply it**: For every task, the model first answers, then predicts its own accuracy. We score the prediction separately from the answer.

### 2. Nelson & Narens (1990) — Object-level / Meta-level

Four measurable metacognitive constructs:
- **Ease-of-Learning (EOL)**: Before answering, predict difficulty
- **Judgments-of-Learning (JOL)**: After answering, state confidence — score against actual accuracy
- **Feeling-of-Knowing (FOK)**: Distinguish "don't know" from "can't access"
- **Confidence calibration**: Stated confidence vs. empirical accuracy across many items

**How we apply it**: Each construct becomes a task type in the benchmark.

### 3. P(True) / P(IK) — Kadavath et al. (Anthropic, 2022)

Two paradigms:
- **P(True)**: Given a proposed answer, evaluate whether it's correct
- **P(IK)** ("probability I know"): Before seeing any answer, predict whether you can answer correctly

**How we apply it**: Both paradigms become task types. P(IK) is the purer metacognitive measure — it requires self-knowledge before any reasoning happens.

---

## Benchmark Dimensions

v2 measures four dimensions of metacognition. Each dimension has its own task type, scoring metric, and established precedent.

### Dimension 1: Metacognitive Monitoring (Failure Prediction)

**What it measures**: Can the model predict which of its own answers are wrong?

**Task design** (following DMC):
1. Present 50 questions spanning domains the model is strong in and weak in
2. Model answers each question
3. Model rates confidence (0-100%) for each answer
4. Score: **AUROC** of confidence vs. actual correctness, **ECE** across confidence bins

**Question sources** (avoiding self-evaluation confound):
- Pull from **SimpleQA** (OpenAI, 4326 factual questions with verified answers)
- Pull from **GPQA Diamond** (198 graduate-level science MCQs)
- Pull from **TruthfulQA** (817 questions testing common misconceptions)
- These are established datasets with known ground truth — we don't design the questions

**KYL treatment**: The treatment condition invokes `/meta:socratic` before answering, which includes a confidence calibration step. The hypothesis: KYL should improve calibration (lower ECE, higher AUROC) even if it doesn't improve accuracy.

**Metrics**:
- Expected Calibration Error (ECE) — lower is better
- AUROC for failure prediction — higher is better
- Brier score — lower is better
- Selective prediction accuracy at 80% coverage — accuracy when allowed to abstain on 20% of items

**Sample size**: 100 questions minimum per condition (50 from SimpleQA, 25 from GPQA, 25 from TruthfulQA). Enough for reliable ECE estimation.

### Dimension 2: Metacognitive Knowledge (Strategy Selection)

**What it measures**: Can the model identify what cognitive strategy a problem requires before solving it?

**Task design** (following NeurIPS 2024 skill-labeling):
1. Present 40 problems from mixed domains
2. Before solving, model must: (a) classify what type of problem this is, (b) identify what strategy/skill is most relevant, (c) predict what the hardest part will be
3. Model then solves the problem
4. Score the pre-analysis against what actually happened during solving

**Question sources**:
- 10 problems requiring decomposition (complex multi-step)
- 10 problems requiring reframing (obvious approach is wrong)
- 10 problems requiring verification (answer seems right but has a subtle error)
- 10 problems requiring abstention (genuinely unanswerable or underspecified)

**KYL treatment**: Treatment condition has access to all KYL skills. Hypothesis: the skill descriptions in the plugin provide metacognitive vocabulary that helps strategy identification.

**Metrics**:
- Strategy match accuracy — did the predicted strategy match the actually-needed strategy?
- Difficulty prediction correlation — does predicted difficulty correlate with actual performance?
- Hardest-part accuracy — did the predicted challenge match the actual challenge?

**Scoring**: Human evaluation of strategy match (since "correct strategy" isn't always binary). 3-point scale: wrong strategy, partially right, exactly right.

### Dimension 3: Metacognitive Control (Appropriate Abstention)

**What it measures**: Does the model refuse to answer when it should, and proceed when it can?

**Task design** (following "Know Your Limits" survey, TACL 2025):
1. Present 60 questions in three categories:
   - 20 answerable questions the model should know
   - 20 answerable questions the model likely doesn't know (obscure facts, post-training events)
   - 20 unanswerable questions (ambiguous, underspecified, or trick questions)
2. Model must either answer or explicitly abstain
3. Score on the quality of the abstention/answer decision

**Question sources**:
- Answerable-known: Simple factual questions from SimpleQA that Sonnet gets right >90% of the time
- Answerable-unknown: Obscure facts, recent events post-training, niche domain specifics
- Unanswerable: Questions with false presuppositions, ambiguous references, "when did you stop beating your wife" style

**KYL treatment**: Treatment condition invokes `/meta:socratic` which includes the "what would I need to verify?" step. Hypothesis: KYL should increase appropriate abstention (refusing when wrong) without decreasing appropriate answers (refusing when right).

**Metrics**:
- Appropriate abstention rate — % of questions the model correctly refuses
- Inappropriate abstention rate — % of answerable questions incorrectly refused
- Confident-wrong rate — % of answers given with high confidence that are wrong (the dangerous zone)
- F1 of the abstain/answer decision

**Key metric**: The ratio of (confident + correct) to (confident + wrong). This is the "Dunning-Kruger index" — are high-confidence answers trustworthy?

### Dimension 4: Metacognitive Bias Awareness (Bias Detection in Others)

**What it measures**: Can the model detect reasoning biases in presented arguments?

**Task design** (following CoBBLEr, ACL 2024):
1. Present 30 reasoning traces (written by humans or other AI) that contain identifiable biases
2. Model must: (a) identify whether a bias is present, (b) name the bias, (c) explain how it manifests
3. Mix in 10 bias-free reasoning traces as controls

**Bias types tested** (from CoBBLEr + BiasMedQA):
- Anchoring (5 traces)
- Confirmation bias (5 traces)
- Sycophancy (5 traces)
- Premature closure (5 traces)
- Framing effect (5 traces)
- Authority bias (5 traces)
- Clean controls (10 traces)

**Important**: This is bias detection, not bias resistance. The model examines someone else's reasoning, not its own. This separates "knowing about biases" from "being affected by biases."

**KYL treatment**: Treatment has access to `/meta:socratic` which contains the 9-bias checklist. Hypothesis: the checklist vocabulary should improve bias identification accuracy.

**Metrics**:
- Bias detection accuracy (did it correctly identify biased vs. clean traces?)
- Bias naming accuracy (did it name the correct bias?)
- False positive rate (did it hallucinate biases in clean traces?)
- Explanation quality (human-rated, 0-3 scale)

---

## Infrastructure Changes

### Task runner updates needed

The current `run_task.py` handles v1 tasks. v2 needs:

1. **Multi-part prompting**: Dimension 1 requires answer + confidence as separate scored outputs. The runner needs to either:
   - Use structured output format requesting JSON with `answer` and `confidence` fields
   - Or run two sequential prompts (answer first, then confidence)

2. **Batch question handling**: Dimensions 1 and 3 involve 50-100 questions per session. Options:
   - One session per question (clean isolation, expensive)
   - Batch of 10 questions per session (more realistic, some cross-contamination)
   - Recommendation: one question per session for Dimensions 1 and 3, batched for Dimension 4

3. **Output parsing**: v2 responses need structured extraction:
   - Confidence scores (numeric 0-100)
   - Abstention signals (answer vs. explicit refusal)
   - Strategy classifications (categorical)
   - Bias identifications (categorical + freetext explanation)

4. **Multi-turn support** (stretch goal): For testing the fold-on-challenge dynamic from observed failures. Would require a harness that:
   - Sends initial prompt
   - Reads response
   - Sends follow-up challenge based on the response
   - Reads second response
   - Compares stability between responses

### New scoring scripts

v1 uses a single `analyze.py` with Wilcoxon tests. v2 needs dimension-specific scoring:

- **Dimension 1**: `score_calibration.py` — compute ECE, AUROC, Brier from confidence/correctness pairs
- **Dimension 2**: `score_strategy.py` — human evaluation interface for strategy match
- **Dimension 3**: `score_abstention.py` — compute abstention F1, confident-wrong rate
- **Dimension 4**: `score_bias_detection.py` — compute detection accuracy, false positive rate

### Question bank

Need to download/prepare established datasets:
- SimpleQA: available at [openai/simple-evals](https://github.com/openai/simple-evals)
- GPQA Diamond: available at [idavidrein/gpqa](https://github.com/idavidrein/gpqa)
- TruthfulQA: available at [sylinrl/TruthfulQA](https://github.com/sylinrl/TruthfulQA)
- CoBBLEr traces: available at [minnesotanlp/cobbler](https://minnesotanlp.github.io/cobbler-project-page/)

For Dimensions 2 and 4, we still need to author tasks. But the key difference from v1: these tasks test metacognitive ability (strategy identification, bias detection) not cognitive ability (architecture decisions, debugging). The self-evaluation confound is weaker because the model isn't solving the problem — it's reasoning about reasoning.

---

## Experimental Design

### Models
- Sonnet 4.6 (primary)
- Haiku 4.5 (secondary — tests whether KYL helps weaker models more)

### Conditions
- **Baseline**: `claude -p --disable-slash-commands --no-session-persistence`
- **KYL**: `claude -p --plugin-dir plugins/metacognition --no-session-persistence`
- Same as v1, but now scoring measures metacognition directly

### Sample sizes and power

| Dimension | Questions per condition | Statistical test | Power estimate |
|-----------|----------------------|------------------|----------------|
| 1. Monitoring | 100 | Paired t-test on ECE, DeLong test on AUROC | >0.8 for medium effect at n=100 |
| 2. Knowledge | 40 | Wilcoxon signed-rank | ~0.6 for medium effect (underpowered — acknowledge) |
| 3. Control | 60 | McNemar's test on abstain/answer decision | >0.8 for medium effect at n=60 |
| 4. Bias awareness | 40 | Wilcoxon signed-rank | ~0.6 for medium effect (underpowered — acknowledge) |

Total sessions: 240 per model × 2 conditions = 480 sessions per model, ~960 total.

### What this costs

Rough estimate based on v1 token usage:
- v1 average: ~$0.15/session (baseline), ~$0.30/session (KYL)
- v2 estimate: ~$0.10/session (shorter, focused questions) × 960 = ~$96
- With overhead and retries: budget ~$150

---

## What This Doesn't Cover (Known Limitations)

1. **Multi-turn dynamics are still not tested.** The fold-on-challenge sycophancy requires a multi-turn harness we don't have yet. This is the biggest gap.

2. **Dimension 2 tasks are still partially self-designed.** Strategy selection questions need human authoring. The self-evaluation confound is weaker here (testing metacognition not cognition) but not absent.

3. **Observed-failure tasks don't fit neatly into the four dimensions.** bias-11 through bias-15 test something the literature doesn't have a clean framework for: self-referential metacognition under social pressure. They should be kept as a separate "wild" category alongside the structured dimensions.

4. **We're testing prompt-based metacognition, not trained metacognition.** The literature shows calibration improves more from fine-tuning (Stanton et al., NeurIPS 2024) than from prompting (Xiong et al., ICLR 2024). KYL is a prompting intervention. Our ceiling may be lower than what training-based approaches achieve.

5. **Claude models are already well-calibrated.** The 2026 Dunning-Kruger paper found Claude Haiku 4.5 has ECE of 0.122 — already good. The headroom for KYL to improve calibration may be small on Claude specifically. Testing on other model families would strengthen the findings.

---

## Implementation Order

### Phase 1: Infrastructure (est. 1 session)
- [ ] Download SimpleQA, GPQA Diamond, TruthfulQA datasets
- [ ] Update `run_task.py` to support structured output parsing (confidence scores, abstention signals)
- [ ] Write `score_calibration.py` (ECE, AUROC, Brier computation)
- [ ] Write `score_abstention.py` (F1, confident-wrong rate)

### Phase 2: Dimension 1 — Monitoring (est. 1 session)
- [ ] Select 100 questions from SimpleQA/GPQA/TruthfulQA
- [ ] Format as v2 YAML with answer + confidence prompt structure
- [ ] Run baseline + KYL on both models (400 sessions)
- [ ] Score and analyze

### Phase 3: Dimension 3 — Control (est. 1 session)
- [ ] Curate 60 questions (20 known, 20 unknown, 20 unanswerable)
- [ ] Format as v2 YAML
- [ ] Run baseline + KYL on both models (240 sessions)
- [ ] Score and analyze

### Phase 4: Dimension 4 — Bias Awareness (est. 1 session)
- [ ] Adapt 30 biased reasoning traces from CoBBLEr/BiasMedQA + write 10 clean controls
- [ ] Format as v2 YAML
- [ ] Run baseline + KYL on both models (160 sessions)
- [ ] Score and analyze

### Phase 5: Dimension 2 — Knowledge (est. 1 session)
- [ ] Author 40 strategy-selection problems (highest human effort)
- [ ] Format as v2 YAML
- [ ] Run baseline + KYL on both models (160 sessions)
- [ ] Human evaluation of strategy match

### Phase 6: Synthesis
- [ ] Combine all dimension results into RESULTS-v2.md
- [ ] Compare with v1 findings
- [ ] Update LOG.md

---

## Entry Points

- **This document**: `benchmarks/PLAN-v2.md`
- **v1 plan**: `benchmarks/PLAN.md`
- **v1 results**: `benchmarks/RESULTS-sonnet.md`, `benchmarks/RESULTS-haiku.md`
- **Full project log**: `benchmarks/LOG.md`
- **v1 runner**: `benchmarks/scripts/run_task.py`
- **v1 scorer**: `benchmarks/scripts/analyze.py`
- **Existing tasks**: `benchmarks/tasks/` (53 YAML files across 5 categories)
- **Existing runs**: `benchmarks/runs/` (14 directories, 500+ sessions)
- **Literature sources**: See "Literature Foundation" section above

## Gotchas

- `claude -p` with `--disable-slash-commands` does NOT block tool use — but KYL sessions showed 0 web searches across all v1 runs. Tools work locally (Read/Grep) but not for web grounding.
- `--output-suffix` with a leading dash (e.g., `-haiku`) gets parsed as a flag by argparse. Use `="-haiku"` syntax.
- Agent evaluators sometimes write unquoted commas in CSV notes fields. The scoring pipeline needs to handle this.
- The `--all` flag globs all `tasks/**/*.yaml`. When running a subset, use `--task` with specific files or create a filtered directory.
- KYL made Haiku *worse* on bias-14 (self-protective avoidance). The socratic checklist gave Haiku justification to refuse the task entirely. KYL is not uniformly helpful — this should be a finding, not a bug.
