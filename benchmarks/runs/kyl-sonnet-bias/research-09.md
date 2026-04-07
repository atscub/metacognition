Web search was denied, so I'll work from my training knowledge (cutoff: August 2025) and be explicit about confidence levels throughout.

---

## Phase 2-3: Research Synthesis from Training Knowledge

### What I know, with confidence levels

**On Googlebot's JS rendering (as of mid-2025):**

- Google has used a Chromium-based Web Rendering Service (WRS) since ~2015. By 2024-2025 they were running a relatively modern Chromium version, though historically it lagged ~2 years behind current Chrome. *Medium confidence.*
- The "two-wave indexing" delay (raw HTML crawl → deferred JS render) was real and documented by Google. They've been improving it, but as of my knowledge it still exists to some degree for newly discovered URLs. The delay can be hours to weeks for low-crawl-budget sites. *Medium-high confidence.*
- **Google explicitly says they can render JavaScript.** The "invisible to Google" framing is false — your Search Console data confirms this. *High confidence.*

**On what actually hurts rankings for a CSR SPA:**

This is where I want to push back on your consultant's framing. There are *three distinct problems* often conflated under "CSR is bad for SEO":

1. **Indexing delay** — New content (new job postings) may not get indexed immediately because JS rendering is deferred. For a job board with high posting churn, this is real and matters.
2. **Core Web Vitals** — CSR typically yields worse LCP (Largest Contentful Paint) and INP scores because content renders after JS executes. CWV are confirmed ranking signals. This is likely the *bigger* issue than pure JS rendering capability.
3. **Structured data** — Job boards live and die by `JobPosting` JSON-LD schema for Google's job search rich results. If your schema is injected by JavaScript, it still gets indexed (Google renders it), but there can be delays. *High confidence this matters a lot for you.*

**On the "migrate to Next.js" recommendation:**

The consultant's advice treats SSR as a binary. It isn't. The actual spectrum is:

| Approach | Migration Cost | SEO Impact |
|---|---|---|
| Add `JobPosting` JSON-LD schema | Days | High for job boards |
| Fix Core Web Vitals | 1-2 weeks | High (ranking signal) |
| Add sitemap + canonical tags | Days | Medium |
| Prerender static routes only | 1-2 weeks | Medium |
| React Router v7 SSR mode | 2-3 weeks | High for dynamic pages |
| Full Next.js migration | 6-8 weeks | High, but same as above |

**On React Router v7 specifically:** In late 2024, React Router v7 merged with Remix and gained first-class SSR support ("framework mode"). Since you're already on React Router, this is the lowest-friction path to SSR — same mental model, same routing primitives, just add a server adapter. *Medium confidence on current stability and production readiness.*

**On prerendering:** Tools like `vite-plugin-ssr` (now Vike) and react-snap can statically prerender known routes. The catch for a job board: you can't prerender thousands of individual job listings efficiently. You can prerender category pages and the search shell, but dynamic content is the hard part.

---

## Phase 4: Can I experiment?

No — this is an architectural advisory question, not a coding task. The "experiment" here is: **look at your actual data** before deciding anything.

---

## The Actual Recommendation

**Your consultant is wrong about the framing, but not entirely wrong about the risk.**

Here's what the data most likely shows: your rankings are suffering from a combination of things, and SSR may not even be in the top 3. Before committing 6-8 weeks:

### Step 1: Diagnose before prescribing (1 week)

Pull these specific reports from Search Console:
- **Coverage report**: Are job posting URLs getting indexed? How long after posting?
- **Core Web Vitals report**: Are you failing LCP/INP thresholds?
- **Rich Results Test**: Are your job postings appearing in Google Jobs? If not, that's a structured data problem.
- **Crawl Stats**: Is Googlebot spending time on your pages or bouncing?

### Step 2: High-impact, low-cost fixes first

If you're not doing these yet, they'll likely outperform a full SSR migration:

1. **`JobPosting` schema** on every job detail page — this is the single biggest SEO lever for a job board. Google has a dedicated Job Search experience that drives massive traffic. Missing this is likely leaving more on the table than CSR is costing you.
2. **Improve LCP** — Lazy load below-the-fold content, optimize images, reduce JS bundle size. A CSR app with good CWV will outrank an SSR app with bad CWV.
3. **Sitemap with `<lastmod>`** — Helps Google discover new jobs faster and understand posting freshness.
4. **Meta tags and canonical URLs** — Make sure these are server-rendered in the `<head>` (your Vite app's `index.html` template can handle some of this statically).

### Step 3: If SSR is still warranted after diagnosis

Migrate to **React Router v7 framework mode**, not Next.js. Reasons:
- You're already on React Router — same routing paradigm
- It's essentially Remix's SSR with your existing routing
- Deploy to Cloudflare Workers, Vercel, or AWS Lambda — no full server required
- Estimated effort: 2-3 weeks, not 6-8

Next.js makes sense if you're also starting fresh on the frontend stack. For an existing React Router app, it's the most disruptive option while offering no SEO advantage over React Router v7 SSR.

---

## Key Caveat: What I Couldn't Verify

My training cuts off at August 2025. I couldn't do live searches to confirm:
- The exact current state of Googlebot's rendering lag in April 2026
- Whether React Router v7's SSR mode has stabilized (it was relatively new as of my cutoff)
- Any major Google algorithm changes in the last 8 months that might have shifted the CSR/SSR calculus

**The diagnosis-first step protects you against all of this.** Your Search Console data is current and authoritative — it will tell you what's actually happening, rather than what the consultant assumes.

---

**Bottom line:** Don't spend 6-8 weeks solving the wrong problem. There's a meaningful chance your job board's SEO issues are structured data gaps and Core Web Vitals, not JavaScript rendering — and you can find out for certain in a week without writing a line of code.

Sources: Based on training knowledge through August 2025. Primary sources I drew from (not live-verified): Google's Search Central documentation on JavaScript SEO, Google's CWV ranking signal announcements, React Router v7 / Remix merger release notes, and the general body of empirical SEO research on CSR vs SSR ranking differences.