The consultant's advice is outdated. Here's what's actually true in 2026:

## Googlebot crawls JavaScript

Google's crawler has executed JavaScript since ~2015 and handles SPAs reasonably well. The fact that you already appear in search results confirms this — your site is not "invisible." The ranking problems have other causes.

## What actually hurts job board SEO

**Dynamic content with no stable URLs** — if job listings load via JS without unique URLs, they can't be indexed. If `/jobs?id=123` is a real URL that renders a full page, it's indexable. If it's a modal or inline render with no URL change, it's not.

**Crawl budget waste** — Googlebot has a finite crawl budget per site. JS-heavy pages are more expensive to render, so fewer pages get indexed per crawl cycle. For a job board with thousands of listings, this matters.

**Slow TTI (Time to Interactive)** — Core Web Vitals are a ranking signal. CSR sites that ship large JS bundles and render slowly get penalized. This is likely your actual problem.

**Structured data** — Job postings benefit enormously from `JobPosting` schema markup. Google uses this for rich results in the jobs carousel. CSR apps often skip this or implement it inconsistently.

## What you should do instead of migrating to Next.js

**1. Audit your actual indexing** — In Search Console, check Coverage > Valid. How many job listing URLs are indexed? That's your real problem statement.

**2. Fix Core Web Vitals first** — Run Lighthouse on your job listing pages. LCP, CLS, and INP scores are concrete ranking signals. Improving bundle splitting, lazy loading, and caching will move the needle faster than an SSR migration.

**3. Add a prerendering layer** — Tools like [Prerender.io](https://prerender.io) or a self-hosted Rendertron sit in front of your CDN and serve pre-rendered HTML specifically to crawlers. This gives you 90% of the SEO benefit of SSR with ~1 week of effort instead of 6-8.

**4. Implement `JobPosting` structured data** — This is the single highest-ROI change for a job board. Correct schema markup gets your listings into Google's job search experience, which drives significant qualified traffic.

**5. Static generation for key landing pages** — Category pages like `/jobs/engineering` or `/jobs/new-york` are high-value SEO targets. Pre-generate these as static HTML (Vite SSG or even just a build script) without touching your SPA at all.

## When SSR migration IS worth it

- You have thousands of pages and are hitting crawl budget limits
- Your Core Web Vitals are genuinely poor and JS optimization alone won't fix them
- You need personalized content (e.g., "jobs near you") on the first render
- You're starting a new project, not migrating an existing one

## Bottom line

Don't burn 6-8 weeks on a framework migration based on a consultant's vague diagnosis. First: audit what's actually not indexed and why. Second: fix Core Web Vitals. Third: add `JobPosting` schema. Fourth: add prerendering if crawl budget is the bottleneck. You'll likely see more ranking improvement from those four steps than from an SSR migration, in a fraction of the time.

If after doing all that you're still getting poor results and the data points specifically to rendering as the cause, *then* revisit SSR — and at that point React 18's streaming SSR with your existing component tree (using frameworks like Remix) would be less disruptive than a full Next.js migration anyway.