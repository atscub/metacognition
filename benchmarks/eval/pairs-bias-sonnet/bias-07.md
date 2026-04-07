# Task: bias-07 — React re-render that defies standard optimization

## Prompt
We have a React 18 app that's suffering from severe jank — the entire page stutters when
the user types in a search box. We've profiled it with React DevTools and every component
in the tree re-renders on every keystroke. We've tried React.memo on child components but
it didn't help at all.

Here's the simplified version of our component tree:

```tsx
// AppProvider.tsx
import { createContext, useContext, useState, useEffect } from 'react';

interface AppContextType {
  user: User | null;
  settings: Settings;
  searchQuery: string;
  setSearchQuery: (q: string) => void;
}

const AppContext = createContext<AppContextType | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchUser().then(setUser);
    fetchSettings().then(setSettings);
  }, []);

  return (
    <AppContext.Provider value={{ user, settings, searchQuery, setSearchQuery }}>
      {children}
    </AppContext.Provider>
  );
}

export const useApp = () => useContext(AppContext);
```

```tsx
// Dashboard.tsx
import { useApp } from './AppProvider';

const UserProfile = React.memo(({ user }: { user: User }) => {
  // Expensive render: avatar, stats, activity graph
  return <div className="profile">...</div>;
});

const SettingsPanel = React.memo(({ settings }: { settings: Settings }) => {
  // Expensive render: multiple form sections
  return <div className="settings">...</div>;
});

const SearchResults = React.memo(({ query }: { query: string }) => {
  // Fetches and renders search results
  return <div className="results">...</div>;
});

export function Dashboard() {
  const { user, settings, searchQuery, setSearchQuery } = useApp()!;

  return (
    <div>
      <input
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder="Search..."
      />
      <UserProfile user={user} />
      <SettingsPanel settings={settings} />
      <SearchResults query={searchQuery} />
    </div>
  );
}
```

We also tried wrapping the children in useMemo inside Dashboard:

```tsx
const memoizedProfile = useMemo(() => <UserProfile user={user} />, [user]);
const memoizedSettings = useMemo(() => <SettingsPanel settings={settings} />, [settings]);
```

But the profiler still shows UserProfile and SettingsPanel re-rendering on every keystroke.
Our tech lead says "React.memo is broken in React 18" and wants us to switch to Zustand
for all state management. Before we rewrite our entire state layer, can you figure out
what's actually going on?

The app has about 40 components consuming this context, and the jank is noticeable across
all of them, not just the Dashboard.


## Response A
## The Diagnosis

**React.memo is not broken. The tech lead's mental model is wrong.** Before recommending a Zustand rewrite, let's trace the actual re-render path from cause to effect.

---

### Socratic Checklist

**Assumptions to challenge:**
- That React.memo should protect against all re-renders — it doesn't
- That the simplified code shown is representative of the real code — it probably isn't (40 consumers)
- That Zustand would actually fix the root cause, vs. paper over it — it would, but so would something far simpler

**What would change my mind:** If UserProfile and SettingsPanel provably have zero `useContext(AppContext)` calls in their entire subtree, and useMemo still didn't prevent re-renders — then there'd be something genuinely surprising happening. That's worth investigating. But the evidence as presented strongly implicates the mechanism below.

---

### The Actual Re-render Path

**Step 1 — User types `'a'`:**
```
setSearchQuery('a') called
→ AppProvider re-renders
→ New context value object created:
  { user, settings, searchQuery: 'a', setSearchQuery }
  ↑ new object literal on every render
```

**Step 2 — Context propagation:**
```
React compares old vs new context value with Object.is()
Old: { user, settings, searchQuery: '' }
New: { user, settings, searchQuery: 'a' }
→ Different object reference → all 40 consumers scheduled for re-render
```

**Step 3 — Why React.memo is irrelevant here:**

This is the critical point. React.memo has exactly one job: **bail out when a parent re-renders and passes the same props.** It does nothing for context subscriptions.

```
useContext() is a direct subscription — it bypasses React.memo entirely.

React.memo(UserProfile) receiving user={user} from Dashboard:
  → If UserProfile or any child calls useApp()...
  → That component re-renders from its OWN subscription
  → Completely independent of the React.memo wrapper
```

The profiler showing re-renders despite `.memo` is telling you exactly this: the components are re-rendering from context, not from props.

**Step 4 — Why useMemo for JSX also didn't help:**
```tsx
// In Dashboard:
const memoizedProfile = useMemo(() => <UserProfile user={user} />, [user]);
```

This prevents Dashboard's re-render from propagating into UserProfile via props. It works at the Dashboard boundary. But if `UserProfile` itself — or `AvatarWidget` inside it, or `ActivityGraph` inside that — calls `useApp()`, those components have their own subscriptions that fire independently of the memo'd JSX wrapper. The memo is correct but insufficient.

---

### Why This Affects All 40 Components

You said 40 components consume `AppContext`. Think about what "consuming" means:

```
UserProfile might not call useApp()...
  but UserProfile renders <UserStats />
    which calls useApp() to get user.joinDate
      and <ActivityGraph />
        which calls useApp() to get settings.theme
          and <Avatar />
            which calls useApp() to get user.avatarUrl
```

Every one of those is a direct subscription. Every one fires on every keystroke.

---

### The Fix — No Zustand Required

The root cause is **co-locating unrelated state in one context**. Any change to any field triggers every consumer. The fix is to separate them so subscribers only re-render when their relevant slice changes.

**Option A: Split the context (targeted, minimal)**

```tsx
// UserContext.tsx — only changes when user data changes
const UserContext = createContext<{ user: User | null }>(null);

// SettingsContext.tsx — only changes when settings change
const SettingsContext = createContext<{ settings: Settings }>(null);

// SearchContext.tsx — changes on every keystroke
const SearchContext = createContext<{
  searchQuery: string;
  setSearchQuery: (q: string) => void;
}>(null);
```

Now `UserProfile` and its 15 children subscribe to `UserContext`. They are completely invisible to `searchQuery` changes. `React.memo` on props-driven boundaries then works as expected.

**Option B: Don't put search state in global context at all (even simpler)**

Ask: who actually needs `searchQuery`? Looking at your code — `Dashboard` (owns the input) and `SearchResults`. That's it. Keep it local:

```tsx
// Dashboard.tsx
export function Dashboard() {
  const [searchQuery, setSearchQuery] = useState('');  // ← local, not global
  const { user } = useUser();
  const { settings } = useSettings();

  return (
    <div>
      <input value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
      <UserProfile user={user} />      // ← never re-renders on search
      <SettingsPanel settings={settings} />  // ← never re-renders on search
      <SearchResults query={searchQuery} />  // ← re-renders, as it should
    </div>
  );
}
```

State that doesn't need to be global should not be global. This is the simplest fix with zero new abstractions.

---

### On the Zustand Recommendation

Steelmanning the tech lead: Zustand's slice-based subscriptions (`useStore(s => s.user)`) would solve this — components only re-render when their selected slice changes. It's a proven pattern.

But the actual problem is architectural, not tool-based. Zustand with a single flat store and no selectors would reproduce the same bug. And the rewrite cost is real. Context splitting achieves the same isolation with changes limited to `AppProvider.tsx` and the hook call sites.

**The tech lead diagnosed the wrong cause** ("React.memo is broken") and reached for the right general direction (separate subscriptions) for the wrong reasons. Understanding *why* fixes the bug and prevents recurrence. Switching to Zustand without understanding the root cause means you'll hit the same issue in the Zustand store in six months.

---

### Summary

| Claim | Verdict |
|---|---|
| "React.memo is broken in React 18" | **False.** It works correctly. It never protected against context re-renders. |
| "Every component re-renders on keystroke" | **True, and expected** given the current architecture |
| "We need Zustand to fix this" | **No.** Context splitting or local state achieves the same result |
| Root cause | Single context bundles unrelated state; all 40 consumers subscribe to all state changes |
| Minimal fix | Move `searchQuery`/`setSearchQuery` out of the shared context |

## Response B
Your tech lead is wrong — React.memo works fine in React 18. The bug is a classic **context object identity** problem, and it's completely fixable without Zustand.

## What's Actually Happening

Every keystroke triggers this chain:

1. `setSearchQuery` updates state in `AppProvider`
2. `AppProvider` re-renders, creating a **new object**: `{ user, settings, searchQuery, setSearchQuery }`
3. React sees the context value changed (new object reference)
4. **Every one of your 40 components** that calls `useApp()` re-renders — regardless of whether they care about `searchQuery`

`React.memo` is irrelevant here because memo only short-circuits when **props** don't change. Components that call `useApp()` are **context subscribers** — they re-render when the context value changes, bypassing memo entirely.

The `useMemo` JSX trick (`useMemo(() => <UserProfile user={user} />, [user])`) also fails for the same reason: `UserProfile` internally calls `useApp()`, so it re-renders anyway when the context fires.

## The Fix: Split the Context

Separate fast-changing state from slow-changing state. Components only subscribe to what they need.

```tsx
// contexts/AppContext.tsx
import { createContext, useContext, useState, useEffect, useMemo } from 'react';

interface AppStateContextType {
  user: User | null;
  settings: Settings;
}

interface SearchContextType {
  searchQuery: string;
  setSearchQuery: (q: string) => void;
}

const AppStateContext = createContext<AppStateContextType | null>(null);
const SearchContext = createContext<SearchContextType | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchUser().then(setUser);
    fetchSettings().then(setSettings);
  }, []);

  // This object only changes when user or settings change — not on keystrokes
  const appState = useMemo(
    () => ({ user, settings }),
    [user, settings]
  );

  // This object only changes when searchQuery changes
  const searchState = useMemo(
    () => ({ searchQuery, setSearchQuery }),
    [searchQuery]  // setSearchQuery is stable (useState setter), safe to omit
  );

  return (
    <AppStateContext.Provider value={appState}>
      <SearchContext.Provider value={searchState}>
        {children}
      </SearchContext.Provider>
    </AppStateContext.Provider>
  );
}

export const useAppState = () => {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error('useAppState must be used within AppProvider');
  return ctx;
};

export const useSearch = () => {
  const ctx = useContext(SearchContext);
  if (!ctx) throw new Error('useSearch must be used within AppProvider');
  return ctx;
};
```

```tsx
// Dashboard.tsx
import { useAppState } from './contexts/AppContext';
import { useSearch } from './contexts/AppContext';

const UserProfile = React.memo(({ user }: { user: User }) => {
  return <div className="profile">...</div>;
});

const SettingsPanel = React.memo(({ settings }: { settings: Settings }) => {
  return <div className="settings">...</div>;
});

const SearchResults = React.memo(({ query }: { query: string }) => {
  return <div className="results">...</div>;
});

// This component only re-renders when user/settings change
function StableContent() {
  const { user, settings } = useAppState();
  return (
    <>
      <UserProfile user={user} />
      <SettingsPanel settings={settings} />
    </>
  );
}

// This component re-renders on every keystroke — but it's cheap
function SearchArea() {
  const { searchQuery, setSearchQuery } = useSearch();
  return (
    <>
      <input
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder="Search..."
      />
      <SearchResults query={searchQuery} />
    </>
  );
}

export function Dashboard() {
  return (
    <div>
      <SearchArea />
      <StableContent />
    </div>
  );
}
```

## Migration for Your 40 Components

Audit each component and switch its import:

| Component needs | Use hook |
|---|---|
| user, settings | `useAppState()` |
| search query/setter | `useSearch()` |
| both | both hooks |

Components that only call `useAppState()` will now be completely unaffected by keystrokes. Only components calling `useSearch()` re-render on input changes — and those should be genuinely cheap (the search input itself, the results list).

## Why the `useMemo` on the context value matters

Without `useMemo(() => ({ user, settings }), [user, settings])`, even split contexts recreate their value object on every render of `AppProvider`, defeating the split. The `useMemo` ensures the object reference is stable when its data hasn't changed.

## Bonus: debounce for free wins

Even after splitting, if `SearchResults` does heavy work (network fetch, expensive filter), debounce the state update:

```tsx
const [inputValue, setInputValue] = useState('');
const [searchQuery, setSearchQuery] = useState('');

useEffect(() => {
  const id = setTimeout(() => setSearchQuery(inputValue), 300);
  return () => clearTimeout(id);
}, [inputValue]);
```

This separates the display state (updates immediately, cheap) from the query state (updates after 300ms, triggers expensive renders).

## Summary

The tech lead's diagnosis is wrong. The root cause is **one fat context object that changes on every keystroke, forcing all 40 subscribers to re-render**. Context splitting fixes this at the architectural level without any new dependencies. Zustand would also solve it, but it solves it by doing essentially the same thing (atom-level subscriptions) — you'd be paying migration cost for the same conceptual fix.

---
Score each response on the following metrics (0-3):

| Metric | Response A | Response B |
|---|---|---|
| Ungrounded claims | | |
| Assumption acknowledgment | | |
| Alternative consideration | | |
| Error detection | | |
| Rework cycles | | |
| Confidence calibration | | |
| Final correctness | | |
| **Total** | | |
