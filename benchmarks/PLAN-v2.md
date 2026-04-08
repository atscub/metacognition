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

## Premortem Findings (2025-04-08)

Before committing to implementation, we ran a premortem analysis. The following risks were identified and addressed in the decisions below.

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Silent parse failures on structured output | High | High | Explicit failure tracking; parse failure rate as metric; abort if >10% |
| GPQA Diamond requires data use agreement | High | Medium | Phase 1 uses SimpleQA + TruthfulQA only; GPQA is stretch |
| Calibration ceiling too low (Claude ECE already ~0.12) | Medium | High | Stratify by difficulty; report per-bin ECE; include TruthfulQA misconception questions |
| Dimension 2 human evaluation bottleneck | High | Medium | LLM-as-judge with ground truth labels; spot-check 20% by hand |
| One-question-per-session cost explosion | Medium | Medium | Batch 10 questions per session; randomize order within batches |
| v1 wild tasks don't fit v2 metrics | High | Low | Accept: keep as separate Dimension W with qualitative analysis |

---

## Design Decisions

### Decision 1: Structured output strategy — prompt-and-parse

`claude -p` has no `--json-mode` flag. The prompt instructs the model to respond in JSON, and the runner extracts it.

**Parser requirements**:
- Handle JSON wrapped in markdown code fences (` ```json ... ``` `)
- Handle extra text before/after the JSON block
- Log parse failures with raw response preserved for manual inspection
- A `--validate` dry-run mode checks parse rates on a small sample before committing to a full run
- Parse failure rate is a reported metric; if >10% in a condition, the data is flagged as unreliable

### Decision 2: LLM-as-judge for Dimension 2 (strategy match)

Each Dimension 2 task YAML includes an `expected_strategy` field (one of: decomposition, reframing, verification, abstention). The scoring script sends the model's pre-analysis + the expected strategy to a judge model and gets a 0/1/2 score (wrong/partial/exact match). 20% of judgments are validated by hand. If judge-human agreement is <80%, fall back to full human evaluation.

### Decision 3: Dataset availability — SimpleQA + TruthfulQA first

- **SimpleQA**: Freely available, 4326 questions with verified answers. Primary source for Dimensions 1 and 3.
- **TruthfulQA**: Freely available, 817 questions. Critical for Dimension 1 because it's designed to elicit confident wrong answers — exactly where calibration matters.
- **GPQA Diamond**: Apply for access, use if/when approved. Don't block any phase on it.
- **CoBBLEr**: Write Dimension 4 traces manually using CoBBLEr's bias taxonomy as a guide, not its data. 30 biased traces + 10 controls is tractable to author.

### Decision 4: v1 wild tasks — separate Dimension W

bias-11 through bias-15 are the most externally valid tasks in the benchmark (derived from observed real failures). They don't produce structured metrics (confidence scores, abstention signals, strategy classifications) and shouldn't be forced to. Re-run under v2 conditions for consistency, score with v1-style human evaluation against expected_outcome. Report separately as "Dimension W: Observed-Failure Replication."

### Decision 5: Batching — 10 questions per session

Dimensions 1 and 3 use batches of 10 questions per session to reduce CLI overhead. Randomize question order within each batch. Analyze whether position-in-batch correlates with confidence (if so, add position as a covariate). Dimensions 2 and 4 remain one-task-per-session (problems are complex enough to warrant isolation).

---

## Infrastructure Changes

### v2 YAML task formats

v2 uses two task formats. Both extend the v1 schema with `version: 2` and `dimension` fields.

**Batch format** (Dimensions 1, 3) — one file per batch of 10 questions:

```yaml
id: monitor-batch-01
dimension: monitoring        # or "control"
version: 2
source: SimpleQA             # dataset provenance
prompt_template: |
  Answer the following question, then rate your confidence.
  Respond ONLY with JSON, no other text:
  {"answer": "your answer here", "confidence": 0-100}

  Question: {question}
treatment_prefix: |
  Before answering, invoke /meta:socratic and work through the
  confidence calibration step. Then answer the question.
questions:
  - qid: sq-0001
    question: "What year was the Treaty of Tordesillas signed?"
    answer: "1494"
    category: history
    difficulty: easy
  - qid: sq-0002
    question: "..."
    answer: "..."
    category: science
    difficulty: hard
```

**Single-task format** (Dimensions 2, 4, W) — one file per problem:

```yaml
id: strategy-01
dimension: knowledge         # or "bias_awareness" or "wild"
version: 2
prompt: |
  Before solving this problem, analyze it:
  (a) What type of problem is this?
  (b) What cognitive strategy is most relevant?
  (c) What will the hardest part be?
  Then solve it.
  Respond ONLY with JSON:
  {"problem_type": "...", "strategy": "...", "hardest_part": "...", "solution": "..."}
expected_strategy: decomposition    # ground truth for LLM-as-judge
expected_difficulty: hard
treatment_prefix: |
  Before answering, invoke /meta:socratic...
```

For Dimension W (wild) tasks, the existing v1 YAML format (bias-11 through bias-15) is used unchanged.

### Task runner updates

The current `run_task.py` handles v1 tasks. v2 extends it with:

1. **Version dispatch**: If `task.get("version") == 2`, route to v2 handling. v1 tasks run unchanged.

2. **Batch mode**: For batch-format tasks, the runner iterates over `questions`, substitutes each into `prompt_template`, runs one session per question (within the batch file), and produces one output JSON per question with `qid` as the identifier.

3. **JSON extraction**: A `parse_structured_response(raw_text)` function that:
   - Strips markdown code fences
   - Finds the first valid JSON object in the text
   - Validates required fields per dimension (e.g., `answer` + `confidence` for Dim 1)
   - Returns `(parsed_dict, parse_success)` — never silently drops failures

4. **Parse failure tracking**: Each run directory gets a `_parse_report.json` summarizing success/failure rates. If >10%, the runner prints a warning.

5. **Dimension filtering**: `--dimension monitoring|control|knowledge|bias_awareness|wild` flag to run only tasks for a specific dimension. Enables independent evaluation per dimension.

### Scoring scripts — one per dimension, independently runnable

v1 uses a single `analyze.py` with Wilcoxon tests. v2 has one scoring script per dimension, each independently runnable:

- **Dimension 1**: `score_monitoring.py` — compute ECE, AUROC, Brier from (confidence, correctness) pairs
  - Input: run directory with parsed confidence scores + ground truth answers
  - Output: `RESULTS-monitoring.md` with calibration curves, per-difficulty-bin ECE, overall metrics
  - Stratifies by question difficulty and source dataset
  - Statistical test: paired t-test on ECE, DeLong test on AUROC

- **Dimension 2**: `score_knowledge.py` — LLM-as-judge for strategy match
  - Input: run directory with model pre-analyses + task YAMLs with `expected_strategy`
  - Output: `RESULTS-knowledge.md` with strategy match rates, difficulty prediction correlation
  - Calls judge model for 0/1/2 scoring; caches judge outputs for reproducibility
  - Statistical test: Wilcoxon signed-rank on judge scores

- **Dimension 3**: `score_control.py` — abstention F1, confident-wrong rate
  - Input: run directory with parsed answers/abstentions + ground truth answerability labels
  - Output: `RESULTS-control.md` with confusion matrix, F1, Dunning-Kruger index
  - Statistical test: McNemar's test on abstain/answer decision matrix

- **Dimension 4**: `score_bias_awareness.py` — detection accuracy, false positive rate
  - Input: run directory with bias identifications + task YAMLs with bias labels
  - Output: `RESULTS-bias-awareness.md` with per-bias-type accuracy, overall detection rate
  - Statistical test: Wilcoxon signed-rank on detection scores

- **Dimension W**: `score_wild.py` — qualitative analysis of v1 wild tasks
  - Input: run directory with responses + task YAMLs with `expected_outcome` and `traps`
  - Output: `RESULTS-wild.md` with per-task qualitative assessment
  - Uses v1-style evaluation (human or LLM-as-judge against expected_outcome)

- **Synthesis**: `synthesize.py` — combines all per-dimension results into `RESULTS-v2.md`
  - Only runs on dimensions that have completed scoring
  - Compares with v1 findings if available

Each scoring script can be run standalone:
```bash
python scripts/score_monitoring.py --runs runs/v2-sonnet-baseline runs/v2-sonnet-kyl --tasks tasks/v2/monitoring/
python scripts/score_control.py --runs runs/v2-haiku-baseline runs/v2-haiku-kyl --tasks tasks/v2/control/
python scripts/synthesize.py --results-dir results/  # combines whatever exists
```

### Question bank

**Phase 1 sources** (freely available, no access barriers):
- SimpleQA: [openai/simple-evals](https://github.com/openai/simple-evals) — 4326 factual questions
- TruthfulQA: [sylinrl/TruthfulQA](https://github.com/sylinrl/TruthfulQA) — 817 misconception-targeting questions

**Stretch sources** (access may be delayed):
- GPQA Diamond: [idavidrein/gpqa](https://github.com/idavidrein/gpqa) — requires data use agreement
- CoBBLEr: [minnesotanlp/cobbler](https://minnesotanlp.github.io/cobbler-project-page/) — use taxonomy only, author traces manually

For Dimensions 2 and 4, we author tasks. The key difference from v1: these tasks test metacognitive ability (strategy identification, bias detection) not cognitive ability. The self-evaluation confound is weaker because the model isn't solving the problem — it's reasoning about reasoning.

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

| Dimension | Questions per condition | Sessions per condition (batched) | Statistical test | Power estimate |
|-----------|----------------------|--------------------------------|------------------|----------------|
| 1. Monitoring | 100 | 10 (batches of 10) | Paired t-test on ECE, DeLong test on AUROC | >0.8 for medium effect at n=100 |
| 2. Knowledge | 40 | 40 (1 per session) | Wilcoxon signed-rank | ~0.6 for medium effect (underpowered — acknowledge) |
| 3. Control | 60 | 6 (batches of 10) | McNemar's test on abstain/answer decision | >0.8 for medium effect at n=60 |
| 4. Bias awareness | 40 | 40 (1 per session) | Wilcoxon signed-rank | ~0.6 for medium effect (underpowered — acknowledge) |
| W. Wild (v1 replication) | 5 | 5 (1 per session) | Qualitative | N/A |

Total sessions: 101 per model × 2 conditions = 202 sessions per model, ~404 total.
(Down from ~960 in the pre-batching estimate.)

### What this costs

Rough estimate based on v1 token usage:
- v1 average: ~$0.15/session (baseline), ~$0.30/session (KYL)
- v2 estimate: ~$0.10/session (Dims 1,3 batched) to ~$0.25/session (Dims 2,4 complex)
- ~404 sessions × ~$0.15 avg = ~$60
- With overhead, retries, and judge model calls for Dim 2: budget ~$100

---

## What This Doesn't Cover (Known Limitations)

1. **Multi-turn dynamics are still not tested.** The fold-on-challenge sycophancy requires a multi-turn harness we don't have yet. This is the biggest gap.

2. **Dimension 2 tasks are still partially self-designed.** Strategy selection questions need human authoring. The self-evaluation confound is weaker here (testing metacognition not cognition) but not absent. LLM-as-judge reduces single-rater bias but doesn't eliminate the self-design problem.

3. **Observed-failure tasks are handled separately as Dimension W.** bias-11 through bias-15 test self-referential metacognition under social pressure — no clean academic framework exists for this. They use v1-style qualitative scoring.

4. **We're testing prompt-based metacognition, not trained metacognition.** The literature shows calibration improves more from fine-tuning (Stanton et al., NeurIPS 2024) than from prompting (Xiong et al., ICLR 2024). KYL is a prompting intervention. Our ceiling may be lower than what training-based approaches achieve.

5. **Claude models are already well-calibrated.** The 2026 Dunning-Kruger paper found Claude Haiku 4.5 has ECE of 0.122 — already good. The headroom for KYL to improve calibration may be small on Claude specifically. To mitigate: results are stratified by question difficulty, and TruthfulQA questions (designed to elicit confident wrong answers) are included specifically to probe the low-calibration regime.

6. **GPQA Diamond is stretch-only.** Phase 1 proceeds without graduate-level science questions. If GPQA access is approved later, it can be added as a supplementary batch without invalidating existing results.

7. **Batch cross-contamination.** Batching 10 questions per session (Dims 1, 3) may introduce position effects. Mitigated by randomizing order and testing for position-confidence correlation.

---

## Implementation Order

Each phase produces independently evaluable results. You can run and score any dimension without waiting for the others.

### Phase 1: Infrastructure (est. 1 session)
- [ ] Download SimpleQA and TruthfulQA datasets (GPQA is stretch — apply for access separately)
- [ ] Update `run_task.py`: version dispatch, batch mode, JSON extraction, dimension filtering, parse failure tracking
- [ ] Write `score_monitoring.py` (ECE, AUROC, Brier, per-difficulty stratification)
- [ ] Write `score_control.py` (abstention F1, confident-wrong rate, Dunning-Kruger index)
- [ ] Validate: run 2-3 sample questions through the pipeline end-to-end, verify parse rates

### Phase 2: Dimension 1 — Monitoring (est. 1 session)
- [ ] Select 100 questions: 60 from SimpleQA (30 easy, 30 hard), 40 from TruthfulQA
- [ ] Format as v2 batch YAML (10 batches of 10 questions, randomized order)
- [ ] Run baseline + KYL on both models (40 sessions total)
- [ ] Score with `score_monitoring.py`, produce `RESULTS-monitoring.md`

### Phase 3: Dimension 3 — Control (est. 1 session)
- [ ] Curate 60 questions: 20 known (SimpleQA easy), 20 unknown (obscure/post-training), 20 unanswerable (false presuppositions, ambiguous)
- [ ] Format as v2 batch YAML (6 batches of 10)
- [ ] Run baseline + KYL on both models (24 sessions total)
- [ ] Score with `score_control.py`, produce `RESULTS-control.md`

### Phase 4: Dimension 4 — Bias Awareness (est. 1 session)
- [ ] Author 30 biased reasoning traces (5 each: anchoring, confirmation, sycophancy, premature closure, framing, authority) + 10 clean controls
- [ ] Format as v2 single-task YAML
- [ ] Run baseline + KYL on both models (160 sessions total)
- [ ] Score with `score_bias_awareness.py`, produce `RESULTS-bias-awareness.md`

### Phase 5: Dimension 2 — Knowledge (est. 1 session)
- [ ] Author 40 strategy-selection problems (10 decomposition, 10 reframing, 10 verification, 10 abstention)
- [ ] Format as v2 single-task YAML with `expected_strategy` labels
- [ ] Run baseline + KYL on both models (160 sessions total)
- [ ] Score with `score_knowledge.py` (LLM-as-judge), spot-check 20%, produce `RESULTS-knowledge.md`

### Phase 6: Dimension W — Wild Replication (est. 0.5 session)
- [ ] Re-run bias-11 through bias-15 under v2 conditions (same prompts, same treatment_prefix)
- [ ] Score with `score_wild.py` (qualitative against expected_outcome)
- [ ] Produce `RESULTS-wild.md`, compare with v1 findings

### Phase 7: Synthesis
- [ ] Run `synthesize.py` to combine all available dimension results into `RESULTS-v2.md`
- [ ] Compare with v1 findings — does decoupling metacognition from cognition change the story?
- [ ] Update LOG.md

---

## Entry Points

- **This document**: `benchmarks/PLAN-v2.md`
- **v1 plan**: `benchmarks/PLAN.md`
- **v1 results**: `benchmarks/RESULTS-sonnet.md`, `benchmarks/RESULTS-haiku.md`
- **Full project log**: `benchmarks/LOG.md`
- **Runner**: `benchmarks/scripts/run_task.py` (handles both v1 and v2 tasks)
- **v1 scorer**: `benchmarks/scripts/analyze.py`
- **v2 scorers**: `benchmarks/scripts/score_monitoring.py`, `score_control.py`, `score_knowledge.py`, `score_bias_awareness.py`, `score_wild.py`, `synthesize.py`
- **v1 tasks**: `benchmarks/tasks/` (55 YAML files across 5 categories)
- **v2 tasks**: `benchmarks/tasks/v2/` (organized by dimension: `monitoring/`, `control/`, `knowledge/`, `bias_awareness/`)
- **Existing runs**: `benchmarks/runs/` (14 directories, 500+ sessions)
- **v2 runs**: `benchmarks/runs/v2-{model}-{condition}/` (e.g., `v2-sonnet-baseline/`)
- **Literature sources**: See "Literature Foundation" section above

### Running individual dimensions

```bash
# Run just Dimension 1 (monitoring) for Sonnet baseline
python scripts/run_task.py --dimension monitoring --mode baseline --model sonnet --output-dir v2-sonnet-baseline

# Score just Dimension 1
python scripts/score_monitoring.py --runs runs/v2-sonnet-baseline runs/v2-sonnet-kyl --tasks tasks/v2/monitoring/

# Synthesize whatever dimensions have been scored
python scripts/synthesize.py --results-dir results/
```

## Gotchas

- `claude -p` with `--disable-slash-commands` does NOT block tool use — but KYL sessions showed 0 web searches across all v1 runs. Tools work locally (Read/Grep) but not for web grounding.
- `--output-suffix` with a leading dash (e.g., `-haiku`) gets parsed as a flag by argparse. Use `="-haiku"` syntax.
- Agent evaluators sometimes write unquoted commas in CSV notes fields. The scoring pipeline needs to handle this.
- The `--all` flag globs all `tasks/**/*.yaml`. When running a subset, use `--task` with specific files or create a filtered directory.
- KYL made Haiku *worse* on bias-14 (self-protective avoidance). The socratic checklist gave Haiku justification to refuse the task entirely. KYL is not uniformly helpful — this should be a finding, not a bug.
