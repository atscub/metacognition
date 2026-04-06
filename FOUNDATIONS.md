# KYL: Research Foundations

This document records the research basis for every significant design decision in the Know Your Limits (KYL) metacognition plugin. It is intended for human readers — contributors, evaluators, and anyone auditing why the plugin is built the way it is. It is not loaded by the model at runtime.

---

## 1. Why Prompt-Based Metacognition (Not Architectural)

KYL works entirely through prompts and skill invocations. No fine-tuning, no architectural modification, no separate model component. This choice was deliberate.

Prompt-based metacognition composes with any model without retraining. A user on Claude 3, Claude 4, or a local Mistral instance can install KYL and get the same cognitive operations. Architectural approaches — adapter layers, reinforcement learning from human feedback, or chain-of-thought distillation — require ML expertise and infrastructure that most users do not have. Prompt-based approaches are also iterable: if a bias check produces false positives, you edit a markdown file. You do not retrain a model. This puts the improvement loop in the hands of the person who best understands the failure mode.

A common objection is that prompts cannot force the model to use tools. The CRITIC paper dissolves this objection: in the CRITIC architecture, tool calls are model-initiated in response to a prompt that instructs the model to verify its outputs externally. The tool call is not externally enforced by a harness — it arises from a prompt that makes verification the natural next action. KYL's external grounding mandate (see Section 4) follows the same pattern.

- Wang & Zhao, "Metacognitive Prompting Improves Understanding in LLMs" (NAACL 2024) — showed structured cognitive operations outperform generic chain-of-thought prompting. https://arxiv.org/abs/2308.05342
- Gou et al., "CRITIC: LLMs Can Self-Correct with Tool-Interactive Critiquing" (ICLR 2024) — tool calls are prompt-initiated, not externally enforced. https://arxiv.org/abs/2305.11738

---

## 2. Why Named Biases with Named Mitigations Beat Generic Advice

Early versions of KYL's socratic skill simply instructed the model to "check for biases." This is approximately useless. "Check your biases" is advice that sounds actionable but provides no grip. The model has no handle to grab.

The current design names each bias and pairs it with a concrete mitigation question. "Check for sycophancy" becomes "Am I agreeing because the user is right, or because they pushed back?" "Check for anchoring" becomes "If I had seen the second approach first, would I still prefer my current answer?" Specificity is the mechanism. The difference between generic and specific advice is the difference between "be careful" and "check whether the ladder feet are on firm ground before climbing."

This is not a novel insight about LLMs specifically — it matches what the metacognitive prompting literature finds across many cognitive tasks. LLMs contain bias-awareness information encoded during pretraining. They have read Kahneman, they have encountered discussions of anchoring and availability heuristics. The problem is activation: that knowledge does not surface without a prompt that specifically elicits it. Named biases with named mitigations are the elicitation mechanism.

- Wang & Zhao, "Metacognitive Prompting Improves Understanding in LLMs" (NAACL 2024). https://arxiv.org/abs/2308.05342
- "Could You Be Wrong: Metacognitive Prompts for LLMs" (MDPI 2026) — LLMs contain bias-awareness information but need prompting to surface it. https://www.mdpi.com/2673-2688/7/1/33

---

## 3. Why Steelman Merged into Socratic

KYL originally had a separate `/meta:steelman` skill. It was removed and its operations were absorbed into `/meta:socratic`.

The decision was straightforward: three of steelman's four operations mapped directly to bias rows already present in socratic. Steelmanning the opposing view is the mitigation for sycophancy. Fairly representing the approach you rejected is the mitigation for anchoring to your first solution. Taking an unfamiliar pattern seriously before dismissing it is the mitigation for pattern-matching dismissal. Running steelman after socratic would have meant executing the same cognitive operation twice under different labels.

A separate skill also created a false routing choice. Users would face "should I run steelman or socratic here?" when the answer was almost always "socratic already includes what steelman does." Merging eliminated the routing confusion and reduced the skill surface area without losing capability. The steelman disposition is now the default epistemic stance within socratic, not a separate invocation.

This is internal design analysis. No external reference is required; the merge is justified by inspection of the overlap matrix (see Section 7).

---

## 4. Why External Grounding Is Mandated in Specific Skills

Self-correction without external feedback does not reliably improve output quality. This is one of the more counterintuitive findings in recent LLM research, and it has direct implications for how metacognitive skills must be designed.

Huang et al. (2024) demonstrated that when an LLM is asked to review and improve its own reasoning without any external signal, performance does not improve and sometimes degrades. The model has no new information — it is iterating on its own beliefs. The CRITIC paper provides the complement: when self-correction is grounded in tool calls that retrieve external evidence, performance improves. The mechanism is external falsifiability, not introspection.

KYL therefore mandates tool-grounded verification in three specific skills: socratic (which can make factual claims about the domain), coherence (which checks whether components agree with each other and with external specifications), and premortem (which predicts failure modes that may already be documented). Two skills — reframe and decompose — perform analytical operations on problem framing. They are not making factual claims about the world; they are restructuring how a problem is represented. External grounding is not applicable to restructuring operations. The mandate is scoped to skills that assert facts.

- Gou et al., "CRITIC: LLMs Can Self-Correct with Tool-Interactive Critiquing" (ICLR 2024). https://arxiv.org/abs/2305.11738
- Huang et al., "Large Language Models Cannot Self-Correct Reasoning Yet" (ICLR 2024). https://arxiv.org/abs/2310.01798

---

## 5. Why Selective Triggering (Cost-of-Error Test)

KYL skills are not invoked on every response. Each skill's frontmatter declares when NOT to use it. This is not a convenience feature — it is a correctness requirement.

The Reflexion paper established that verbal reinforcement is most useful after failure, not after every output. Wrapping every response in a reflection loop adds latency and cognitive overhead; more importantly, it can hurt performance on tasks where the initial answer was already correct. A model asked to reconsider a correct answer may produce a worse one. Metacognitive overhead is only justified when the error cost exceeds the analysis cost.

The SOFAI-LM work extends this: in a system that explicitly separates fast intuitive processing from slow deliberative reasoning, looping once or twice is often enough. There is no benefit to indefinite reflection — eventually you are iterating on noise. KYL operationalizes the cost-of-error test through each skill's "when not to use" frontmatter, which lists task types where the skill adds no value or actively degrades output (e.g., decompose is not useful when the problem is already well-specified; reflect is not useful after routine tasks with no novel failure modes).

- Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning" (NeurIPS 2023) — reflection after failure, not after every output. https://arxiv.org/abs/2303.11366
- SOFAI-LM — "looping once or twice is often enough." https://arxiv.org/abs/2508.17959
- IBM coverage of SOFAI-LM: https://www.ibm.com/think/news/can-ai-second-guess-itself

---

## 6. Why the Playbook Pattern

KYL includes a playbook mechanism: after a reflect session, successful reasoning patterns can be extracted and saved to a reusable playbook file. Future sessions can retrieve these patterns when facing similar problems.

The research basis is Metacognitive Reuse (Didolkar et al., 2025). The key finding: when an LLM is prompted to extract reusable reasoning strategies from solved problems and apply those strategies to new problems, performance improves significantly — 46% token reduction and 10% accuracy gain compared to solving from scratch. The mechanism is not memorization of solutions; it is abstraction of problem-solving approach. The agent learns "how to think about this class of problem" rather than "what the answer to this specific problem was."

The playbook operationalizes this without requiring retraining. Rather than embedding patterns in model weights (which requires fine-tuning), the playbook makes patterns explicit and retrievable as text. This is the agent equivalent of what Gary Klein calls Recognition-Primed Decision Making: expert practitioners do not laboriously compare all options when facing a familiar problem type. They recognize the pattern and apply a known solution template, adjusting for the specifics of the current case. The playbook gives the agent a similar capability — not through training, but through explicit, human-editable pattern storage.

- Didolkar et al., "Metacognitive Reuse" (Meta AI, 2025) — 46% token reduction, 10% accuracy gain from reusing reasoning strategies. https://arxiv.org/abs/2509.13237
- Klein, "Sources of Power: How People Make Decisions" (1998) — Recognition-Primed Decision Making: experts recognize patterns and apply known solutions rather than comparing options.

---

## 7. Why Each Skill Exists Separately

KYL has seven skills. They all involve "checking your thinking." This raises the obvious question: why not one skill?

The answer is that each skill performs a distinct cognitive operation at a distinct point in the task lifecycle. Surface overlap in natural language description ("think more carefully") conceals operational differences in what is actually being done and when.

| Skill | Cognitive Operation | When |
|---|---|---|
| Socratic | Bias detection and epistemic calibration | Ongoing mode shift for high-stakes decisions |
| Premortem | Prospective failure analysis | Pre-action |
| Reflect | Retrospective analysis | Post-action, after fail→recover→succeed |
| Reframe | Perspective rotation | When stuck, try different angles |
| Decompose | First-principles reconstruction | When pattern-matching demonstrably fails |
| Learn | Knowledge acquisition with external validation | When ignorant of the domain |
| Coherence | Cross-component consistency audit | When multiple parts must agree |

A single "think harder" skill would produce one of two failure modes: it either becomes so generic that it provides no grip (see Section 2), or it tries to do all seven operations every time, which violates the cost-of-error principle (see Section 5). Distinct skills allow selective invocation. The user or the orchestrating agent can choose the right cognitive operation for the current situation rather than triggering all of them or none of them.

The overlap that does exist — premortem and reflect both analyze failure; socratic and decompose both challenge assumptions — is not a problem. They share a subject matter (risk, uncertainty, assumptions) but apply different operations (prospective vs. retrospective; bias-checking vs. first-principles reconstruction). The operations are not interchangeable.

---

## 8. The 30% Premortem Figure

The premortem skill's description references a 30% improvement in identifying future failure modes. This number comes from empirical research on prospective hindsight.

Mitchell, Russo, and Pennington (1989) studied how people explain events depending on whether they imagine the event as having already occurred versus as a future possibility. When subjects imagined that an event had already happened, they generated more reasons explaining it — and generated them faster — than subjects who imagined the same event as a future possibility. The mechanism is that "already happened" unlocks causal storytelling: the brain is practiced at explaining the past and readily generates causal chains. Imagining a future failure as a past fact borrows this narrative capacity.

The premortem operationalizes this directly: "It is six months from now. This project failed. What happened?" The fictional past-tense framing is not rhetorical decoration — it is the cognitive mechanism that makes the technique work. Klein's 2007 HBR piece documents how this translates into practical team decision-making and reports the approximately 30% figure for increased identification of failure reasons.

- Mitchell, Russo & Pennington, "Back to the Future: Temporal Perspective in the Explanation of Events" (Journal of Behavioral Decision Making, 1989)
- Klein, "Performing a Project Premortem" (Harvard Business Review, 2007). https://cltr.nl/wp-content/uploads/2020/11/Project-Pre-Mortem-HBR-Gary-Klein.pdf

---

## 9. The Falsification Principle

Several KYL skills — particularly socratic and coherence — include an explicit falsification mandate: make a tool call that could disprove your current belief. This is stronger than the CRITIC-style "verify your output." It demands active disconfirmation.

The psychological baseline is Wason's selection task (1960): when asked to test a rule, people overwhelmingly select evidence that would confirm the rule rather than evidence that would refute it. Confirmation bias is not a character flaw; it is the default operating mode of human cognition. The same bias appears in LLM outputs — when asked to support a position, the model generates supporting evidence; the disconfirming evidence does not surface unless specifically solicited.

Popper's falsification criterion provides the normative standard: a belief is well-grounded only if you have made a genuine attempt to disprove it and failed. Seeking confirmation is cheap — you will almost always find some evidence that supports any view. Seeking disconfirmation and not finding it is meaningful. KYL's falsification mandate operationalizes this at the agent level: before committing to a factual claim, make a tool call specifically designed to find evidence against it. The CRITIC paper's tool-checking is necessary but not sufficient — CRITIC checks whether the output is consistent with retrieved information. The falsification protocol is stronger: it requires actively searching for the evidence that would make the current belief wrong.

- Wason, "On the failure to eliminate hypotheses in a conceptual task" (Quarterly Journal of Experimental Psychology, 1960) — people naturally seek confirming evidence, not disconfirming
- Popper, "The Logic of Scientific Discovery" (1959) — a theory is scientific only if it makes predictions that could be proven wrong
- Gou et al., "CRITIC: LLMs Can Self-Correct with Tool-Interactive Critiquing" (ICLR 2024) — tool calls designed to check outperform tool calls designed to support. https://arxiv.org/abs/2305.11738
