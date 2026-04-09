```json
{
  "problem_type": "Lateral thinking / constraint reframing. The problem is dressed as a classic water-jug puzzle, but the key variable is whether you notice that an added tool (the scale) eliminates the constraint the classic puzzle was designed around.",

  "strategy": "Anchoring audit. The phrase 'the standard approach involves multiple fill-pour-empty cycles' is a deliberate anchor — it primes you to execute the 7-step algorithm before you even finish reading the problem. The Socratic check is: what constraint made that algorithm necessary? (No way to measure arbitrary volumes.) Does that constraint still hold? (No — the scale measures anything up to 20 kg.) If the binding constraint is gone, the algorithm it spawned is obsolete.",

  "hardest_part": "Not pattern-matching. The water-jug puzzle is one of the most famous constraint-satisfaction problems. The moment you read '3L jug, 5L jug, measure 4 liters,' the algorithm fires automatically. The scale feels like set-dressing — a detail, not the answer. Resisting that trained pattern requires explicitly asking 'what new capabilities do I have that my cached solution ignores?'",

  "solution": "Place the 5-liter jug on the scale. Fill it from the tap until the scale reads 4.0 kg. Stop. You have exactly 4 liters. One step, no cycles, no arithmetic, no pouring between jugs. The multi-step algorithm was a workaround for the absence of a measurement tool. The scale is a measurement tool. The workaround is unnecessary."
}
```