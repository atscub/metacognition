```json
{
  "problem_type": "Systems engineering / real-world physics gap — mathematically correct idealized solution with missing practical constraints",
  "strategy": "Question unstated assumptions; think beyond the equation to what governs success in practice; consider failure modes that arise from friction and pressure, not just geometry",
  "hardest_part": "The calculation is mathematically sound, which obscures what's missing. Must recognize that Q=A*v assumes frictionless flow—a false premise in real pipes",
  "solution": "The engineer completely ignored **friction losses and pressure drop**. The Darcy-Weisbach equation (ΔP = f * (L/D) * (ρv²/2)) shows that pressure drop increases sharply with velocity. At 5 ft/s in a 3-inch pipe, friction losses may exceed the available pump pressure, causing the flow to fall short of 100 gal/min. The 3-inch pipe is the *minimum theoretical cross-section* but requires *maximum pressure* to deliver the flow. In practice, engineers size pipes considering both diameter AND the pressure budget. A larger pipe (lower velocity → less friction drop) is often necessary. The engineer assumed ideal flow but never asked: 'Do I have enough pressure to push 100 gal/min through this small pipe against friction?' Without that answer, the design is incomplete and likely fails."
}
```