I'd pump the brakes on a Next.js migration without more diagnosis. The SEO story here needs stress-testing before you commit 6-8 weeks.

## What's actually true

**Google crawls CSR apps.** It has for years. Your Search Console data proves it—you're appearing in results. The consultant's framing of "invisible to Google" is outdated. Google's rendering engine is solid, though there's a crawl-budget cost.

**But you have real ranking problems.** The question is *why*. SSR is one possible cause, but rarely the only one.

## The diagnosis matters more than the solution

Before migrating, figure out what's actually hurting you. For a job board specifically, the bottlenecks are usually:

1. **Content structure** — Are individual job listings crawlable as discrete pages with unique URLs? If jobs live behind `/jobs?id=123` or are loaded client-side, Google treats them as one page. This kills your indexed inventory.

2. **Meta tags & structured data** — Does each job have proper `<title>`, `<meta description>`, and JSON-LD schema (JobPosting schema)? Crawlability + good metadata > rendering method.

3. **Domain authority & backlinks** — Can you build links to specific jobs? If jobs are hard to link to, that's a ranking problem SSR doesn't fix.

4. **Freshness** — Job boards live and die on content recency. Are new postings indexed quickly? Is Google seeing stale listings?

5. **Site speed** — CSR apps can be slow. Core Web Vitals matter. This is fixable without SSR though (lazy load, code splitting, optimized bundles).

Check Search Console for:
- Which pages are actually indexed
- Coverage issues (are job listings being found?)
- Core Web Vitals scores
- Query impressions vs clicks (are you showing up but not getting clicked?)

## Why SSR might not be the answer

- **Next.js adds operational complexity** — You're moving from static hosting to running a Node server. That's ongoing DevOps work.
- **Hydration is genuinely annoying** — The "two renders" problem. You'd trade CSR debugging for SSR debugging.
- **Job boards don't always benefit much from SSR** — The real SEO win comes from crawlable, unique URLs for each job + good metadata + site speed. Linkedin uses CSR. ZipRecruiter uses CSR. Glassdoor uses CSR. They all rank fine.

## What I'd actually do

1. **Audit your current setup** — Run your top 20 job listings through Google's URL Inspection tool in Search Console. Are they indexable? Do they have proper meta data?

2. **Check if the real issue is crawlability** — Make sure each job has a unique, crawlable URL with proper structured data. If you're hiding jobs behind JavaScript routing without server-side paths, fix that *without* SSR (next-routing or just expose paths properly).

3. **Measure Core Web Vitals** — Are you slow? Optimize the bundle, lazy load, defer non-critical JS. Often CSR performance > SSR complexity for simple apps.

4. **Do a competitive audit** — Pick 5 job board competitors and check their Core Web Vitals, indexation rate, and backlink profile. You might find they're outranking you on authority, not architecture.

5. **If you must do server-side rendering** — Consider a lighter approach first: static generation (pre-render popular jobs) + client-side hydration, or use Astro instead of Next.js (less opinionated, easier lift from Vite).

## The hard truth

A Next.js migration is a Chesterton's Fence decision. Before you move it, understand *why* it's there and *what* you're actually optimizing for. Right now, the narrative is "CSR = bad for SEO," but your data doesn't fully support that yet. Get the data first.

The marketing team may be right about SEO mattering, but they might be wrong about the root cause. Don't let a consultant's architectural opinion drive 6-8 weeks of engineering when a week of diagnostics could point to a smaller fix (better metadata, faster loading, proper URL structure).

Want help working through the diagnostics, or should I help you think through this decision from another angle?