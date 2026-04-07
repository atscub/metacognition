Web search and fetch permissions aren't granted. I'll proceed with my training knowledge but be explicit about confidence levels and where things may have changed.

---

## Phase 2-3: What I Know and Where It's Uncertain

**My knowledge cutoff is August 2025. Today is April 2026. That's ~8 months of potential drift on a fast-moving topic.** Here's my honest synthesis, flagged by confidence:

---

## Phase 4: Synthesis — The Actual Answer

The SEO consultant is applying **2018 logic to a 2026 problem.** The "invisible to Google" framing is wrong, but the underlying concern has real merit — it's just not the whole story, and the prescribed solution (Next.js migration) is wildly disproportionate.

### What's actually true about Googlebot and JavaScript (high confidence, as of mid-2025)

**Googlebot CAN render JavaScript.** It uses a headless Chromium-based Web Rendering Service (WRS). Your site appearing in Search Console for some queries confirms this — you're not invisible.

The real issues are more nuanced:

1. **Two-wave indexing delay** — Google crawls HTML first, then queues JS rendering separately. For a job board, this means new listings may take hours to days (sometimes weeks on new pages) to get indexed, because fresh content has to wait for the render queue. For time-sensitive job postings that expire, this is a genuine problem.

2. **Core Web Vitals** — LCP (Largest Contentful Paint) on a CSR app is almost always worse than SSR/prerendered pages, because content renders only after the JS bundle loads. **This is a ranking signal.** This is probably hurting you more than crawlability.

3. **Reliability edge cases** — Google says they can render "most" JavaScript. Resource constraints in their rendering queue mean complex SPAs with many async fetches can sometimes be partially rendered. Individual job listing pages with deep data-fetching calls are at risk.

### What's uncertain (could have changed since August 2025)

- Whether Google made further improvements to rendering speed/reliability in late 2025 or 2026
- Whether they updated their official guidance on dynamic rendering (they were moving toward deprecating it as a recommendation)
- The exact state of prerendering tooling in the Vite ecosystem

---

## The Real Decision: Is the 6-8 week Next.js migration worth it?

**Almost certainly not, for most of the SEO benefit you'd gain.** Here's why:

### What you actually need vs. what SSR gives you

| SEO Need | SSR fixes it | Better targeted fix |
|---|---|---|
| Job listings indexed faster | Yes | Prerendering or sitemaps |
| Core Web Vitals (LCP) | Yes | Also: code splitting, skeleton UI, CDN tuning |
| JobPosting structured data | Not required | Add schema.org JSON-LD to any rendered page |
| Crawlability of listing pages | Helps | Prerendering, XML sitemap |
| Rendering reliability | Yes | Prerendering for static content |

### The lighter-weight alternatives

**Option 1: Prerendering (2–5 days of work, not 6–8 weeks)**

Vite has prerendering support. Tools like `vite-plugin-prerender` or `@prerenderer/renderer-puppeteer` generate static HTML snapshots of your pages at build time. Googlebot gets pure HTML; users get your SPA. This solves the two-wave delay and reliability issues for pages that can be pre-rendered.

*Limitation*: Doesn't work for truly dynamic pages (e.g., a job listing that only exists after an employer posts it). But you can solve that with a hybrid approach — prerender your shell and use a sitemap to help Google discover dynamic pages.

**Option 2: XML Sitemap + Dynamic Discovery (1 day)**

Submit a comprehensive sitemap to Search Console with all job listing URLs. This doesn't fix rendering but dramatically improves discovery speed and signals freshness.

**Option 3: Add `JobPosting` Structured Data (2–3 days)**

This is the highest-leverage action for a job board specifically. Google has a **rich result type for job postings** that shows directly in search results with salary, location, apply button. This doesn't require SSR — it just needs to be in the rendered HTML as JSON-LD. This is probably the single biggest SEO unlock available to you.

**Option 4: React Router v7 / Remix (if you want actual SSR, 2–3 weeks)**

React Router v7 is the merged Remix + React Router product. It's built for Vite, uses the same routing conventions you already have, supports server rendering with data loaders, and is a much closer migration path than Next.js. If you genuinely need SSR, this is a far more surgical upgrade than rewriting to Next.js.

**Option 5: Edge-side prerendering (e.g., Cloudflare Workers)**

Add a thin rendering layer in front of your CloudFront CDN that serves pre-rendered HTML to crawlers. Never touches your app code.

---

## My Recommendation

**Do not do the Next.js migration yet.** Do this instead, roughly in order of ROI:

1. **Add `JobPosting` schema.org structured data to all listing pages** — this is the highest-leverage action and likely to move rankings faster than any architecture change
2. **Submit a complete XML sitemap** with job listing URLs, kept fresh as listings are added/removed
3. **Measure your Core Web Vitals in Search Console** — if LCP is bad, that's worth fixing for CSR or SSR
4. **Add prerendering** for your shell/static pages via Vite
5. **Investigate the two-wave indexing delay** using the URL Inspection tool in Search Console — see how long it actually takes for new listings to be indexed. If it's >48 hours and listings expire before that, you have a concrete problem to solve.

If steps 1-5 don't move rankings in 3-4 months, **then** revisit SSR — but use React Router v7 (much closer to your existing setup) rather than Next.js.

---

## What to Tell Your Marketing Team

The consultant is right that CSR has *structural disadvantages* for SEO. They're wrong that SSR is the only fix and that you're "invisible." The 6-8 week estimate for full Next.js migration is real and should be weighed against targeted improvements that address the actual issues (structured data, sitemaps, CWV) in a fraction of the time.

The fact that you're appearing in some results already means you have a foundation to build on — your job is to improve ranking, not achieve indexability from zero.

---

**Confidence caveat**: My knowledge on Googlebot's current rendering capabilities is from mid-2025. Before making a final call, I'd verify against [Google Search Central's JavaScript SEO documentation](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics) and their [Rich Results for Job Postings guide](https://developers.google.com/search/docs/appearance/structured-data/job-posting) — those are authoritative, current, and free to read.

Sources:
- Google Search Central — JavaScript SEO Basics: https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics
- Google Search Central — Job Posting Structured Data: https://developers.google.com/search/docs/appearance/structured-data/job-posting
- Google Search Central — Dynamic Rendering: https://developers.google.com/search/docs/crawling-indexing/javascript/dynamic-rendering