This deserves honest analysis, because the answer isn't what your marketing team thinks, but their core concern *is* valid.

## The SEO Reality

**Google CAN index client-rendered SPAs.** This has been true since ~2018. Google's crawler executes JavaScript reasonably well. Your appearance in search results proves it's working. The "CSR is invisible" narrative is outdated and causes real harm to engineering priorities.

**However, you do have real SEO problems — just not the one they diagnosed.**

## What Actually Matters for Job Board Rankings

1. **Core Web Vitals** (30% of ranking signal) — LCP, FID, CLS. These are *performance metrics*, not "CSR vs SSR." A well-optimized CSR app beats a sluggish SSR app.

2. **Meta tags & OG data** — Job listings need dynamic meta tags (title, description, image) for each job. This affects both Google's understanding and social sharing. CSR can handle this with a meta tag manager.

3. **Structured data** — JSON-LD schema markup for job postings. Critical for rich snippets. Works in both CSR and SSR.

4. **Crawlability** — Your listing pages need to be discoverable. CSR handles this, but you may need to:
   - Emit a sitemap (or dynamic one)
   - Ensure robots.txt isn't blocking your app
   - Give Google clean URLs (not hash-based routing)

5. **Content freshness** — Job listings change often. SSR doesn't help here; you need proper cache headers and feeds.

## The Real Costs You're Avoiding

Migrating to Next.js for job board SEO introduces *real* problems:

- **Hydration complexity** — Dynamic job data must match server-rendered HTML. Flaky.
- **API calls on the server** — You're now fetching data twice (server + client hydration) or dealing with async data serialization.
- **Deployment overhead** — You move from static hosting to running a Node.js server. More ops, more scaling concerns.
- **Build times** — 6-8 weeks is realistic, plus ongoing maintenance tax.
- **Diminishing returns** — Job board pages have low TTI improvement with SSR (most heavy work is in-app interactivity).

## What You Should Actually Do (Ranked by ROI)

**Immediate wins (1-2 weeks):**
1. Audit Core Web Vitals using PageSpeed Insights + Search Console. If you're bad here, fix it first (it's your real problem).
2. Implement dynamic meta tags + OG data in your CSR app (libraries like `react-helmet-async` or native `document.head` manipulation).
3. Add JSON-LD job posting schema markup on listing pages.
4. Verify your sitemap is submitted to Google; check robots.txt isn't over-blocking.

**Medium effort (2-4 weeks):**
1. Pre-render your most important listing pages at build time, or use dynamic SSR *only* for initial page load (hybrid approach).
2. Optimize images, code-split aggressively, defer non-critical JS.
3. Set up proper cache headers (job listings expire quickly; index pages can be cached).

**Only if metrics don't improve:**
- Consider Next.js, but as a targeted solution for job listing pages only, not a full rewrite.

## The Job Board Specificity

Your platform has dynamic content that changes constantly. This actually *works against* SSR:

- Each job page needs fresh data (salary ranges, status, applicant count).
- Pre-rendering all jobs is expensive if you have 10k+ listings.
- Full SSR means your server must hit your API for every request, introducing latency.

Pre-rendering + ISR (incremental static regeneration) or a hybrid CSR/SSR approach is better than full SSR.

## What to Tell Your Marketing Team

*"We appear in search results and are crawlable. The issue is likely page speed (Core Web Vitals) and how we're presenting job data to Google (meta tags, structured data). We're fixing those first—it's 1-2 weeks of work and directly measurable in GSC. If rankings still don't improve, we'll revisit architecture. A Next.js migration would take 6-8 weeks and won't solve the real SEO issues if they're performance or meta-tag related."*

---

**Before committing to any architecture change**, I'd recommend using the `/metacognition:meta:premortem` skill to stress-test the Next.js assumption. Ask: *What would have to be true for the Next.js migration to fail to improve rankings?* (Answer: the real problem is Core Web Vitals or content quality, not CSR.) That reframes the investigation.