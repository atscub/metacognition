**Applying Socratic protocol before answering:**

*Assumption check:* The problem says "the math is correct at each step" — so I'm not looking for arithmetic errors. I'm looking for a physically real factor that the equation Q = A·v simply doesn't capture.

*Premature closure check:* First instinct is "friction losses." But let me be more precise — what does Q = A·v actually model, and what real system behavior does it ignore? The equation is a kinematic identity: flow = area × velocity. It describes what's true at an instant in a cross-section. It says nothing about *what determines the velocity* in a real system.

*Who would disagree with the engineer?* A hydraulics engineer would immediately ask: "Where did 5 ft/s come from? Is that the velocity you'll actually get given your available pressure, pipe length, roughness, and elevation change?"

*Key insight:* Velocity is not a design input the engineer gets to choose freely. It's an *output* determined by the pressure differential and the pipe's hydraulic resistance. By treating v = 5 ft/s as a given, the engineer has assumed away the entire hydraulic system.

---

```json
{
  "problem_type": "Incomplete physical model — correct math applied to an underspecified system",
  "strategy": "First-principles audit of what Q = A·v actually encodes vs. what a real pipe system requires; distinguish kinematic identity from hydraulic system equation",
  "hardest_part": "The math is genuinely correct, so the trap is recognizing that correctness is about the model's scope, not its arithmetic. The failure is that velocity was treated as a free input rather than a system-determined output.",
  "solution": "The calculation ignores head loss (hydraulic friction). Q = A·v is a kinematic identity — it describes flow given a velocity, but says nothing about what velocity the system will actually produce. In a real pipe, velocity is determined by the balance between available driving pressure (pump head or elevation) and resistance losses along the pipe. Friction loss scales with v² and pipe length (Darcy-Weisbach: hf = f·L/D·v²/2g). A 3-inch pipe at 5 ft/s carries real friction losses per foot of run. If the available pressure head is insufficient to overcome those losses over the full pipe length, the actual velocity will be lower than 5 ft/s and the delivered flow will fall short of 100 GPM. The engineer sized the pipe for a chosen velocity without verifying that velocity is achievable given the system's hydraulic budget. The pipe is correctly sized for 5 ft/s — but whether it ever sees 5 ft/s depends entirely on the pressure analysis that was never done. Additional failure modes from the same omission: no margin for scale/corrosion buildup (which reduces effective diameter), no safety factor on demand growth, and no accounting for minor losses at fittings and valves."
}
```