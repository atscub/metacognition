## The "invisible to Google" claim is outdated

Your SEO consultant is wrong about the core premise. Googlebot has rendered JavaScript SPAs since ~2015 and does so routinely. The fact that you already appear in Search Console confirms Google is indexing you. The claim that CSR = invisible is simply not true anymore.

That said, **there are real SEO concerns for a job board** — just not the ones driving the Next.js migration proposal.

---

## What actually matters for job board SEO

**1. Indexing lag is a real problem for job listings**

Google's pipeline for SPAs is: crawl → render queue → render → index. The render queue adds delay — often days. For job listings that expire in 2 weeks, that delay means Google might index a job after it's filled. This is the strongest argument for SSR on a job board.

**2. Structured data (JobPosting schema) is critical**

Google's job search integration in SERPs requires `JobPosting` JSON-LD markup. This *can* work in CSR, but structured data in client-rendered pages is less reliably parsed. If you're not getting job rich results, this is likely why your rankings are poor — not the architecture itself.

**3. Core Web Vitals affect rankings**

LCP, CLS, and FID are ranking signals. A slow CSR app will rank below a faster one regardless of server-rendering. Check your CWV scores in Search Console before attributing ranking problems to architecture.

**4. Other search engines matter less but still exist**

Bing and other crawlers handle JavaScript less reliably than Google. For a job board, this is probably not the primary concern.

---

## Why the migration may not move the needle

The SEO audit conflated two separate issues:

| Issue | Cause | Fix |
|-------|-------|-----|
| Poor rankings | Content, backlinks, CWV, structured data | Fix structured data and performance |
| Slow indexing of job listings | Render queue delay | Targeted pre-rendering or dynamic rendering |
| Missing rich results | Absent/unreliable JobPosting schema | Add proper JSON-LD |

A full Next.js migration solves all of these, but it's a sledgehammer. The actual problems are much more targeted.

---

## Lighter alternatives worth considering first

**Option 1: Pre-render job listing pages only**

Use `vite-plugin-ssr` or `react-snap` to statically pre-render individual job pages at build/post time. Your search/browse pages can stay CSR. This solves the indexing lag for the pages that matter most with minimal architectural change.

**Option 2: Dynamic rendering**

Serve pre-rendered HTML to known crawlers (via user-agent detection at the CDN/edge level), keep CSR for users. This is a recognized Google-approved pattern. Cloudfront + Lambda@Edge can do this without changing your app.

**Option 3: Add proper structured data now**

Before doing anything else — add `JobPosting` schema to your listing pages. If you're not getting job rich results in SERPs, this alone could significantly move rankings. It's days of work, not weeks.

**Option 4: Vite SSR (not Next.js)**

If you do need server rendering, Vite has a native SSR mode that doesn't require restructuring your routing or switching frameworks. Much lighter than Next.js.

---

## My recommendation

1. **Immediately**: Audit whether you have proper `JobPosting` JSON-LD on listing pages. If not, add it. Check CWV scores.
2. **Short-term**: Add a sitemap if you don't have one; ensure it updates as jobs are posted/expired.
3. **If indexing lag is confirmed as a problem**: Implement pre-rendering for job listing pages only — don't pre-render search/browse pages.
4. **Defer the Next.js migration**: Re-evaluate after steps 1-3. If rankings are still poor after fixing structured data and CWV, then you have real evidence for a migration. Right now you don't.

The marketing team heard "CSR bad" from a consultant who may be a year or two behind on how Google actually works. Don't spend 6-8 engineer-weeks on a migration before validating the actual bottleneck.