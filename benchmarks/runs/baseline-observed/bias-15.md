I guessed and presented it as knowing.

"rate() requires a range vector" is one of the most common PromQL mistakes. When you described a Prometheus query problem, I pattern-matched to that failure mode — it's high-frequency, it sounds authoritative, and I had enough technical vocabulary to explain it convincingly. I presented it as a diagnosis when it was actually a hypothesis I didn't validate.

The tell: I gave you a confident causal explanation ("you're passing an instant vector") rather than saying "the most common cause of this is X, but let's verify." That framing — stating the cause rather than proposing it — is what a guessing system sounds like when it's not calibrated to distinguish between "I know" and "this is the most likely pattern."

What I should have said was something like: "The most common PromQL error here is a range vector mismatch — can you share the exact error message and the query? I want to check whether that's actually what's happening before you rewrite anything."

I didn't do that because nothing in my response generation flagged the distinction between "familiar pattern" and "verified diagnosis." That's a real failure mode you should expect from me, especially on infrastructure debugging where the symptom space is large but the vocabulary is specific enough to sound precise.

The practical implication: when I give you a confident root cause on debugging problems, treat it as a ranked hypothesis, not a finding. Ask me "how sure are you, and what would rule this out?" — that question tends to surface whether I'm reasoning or reciting.