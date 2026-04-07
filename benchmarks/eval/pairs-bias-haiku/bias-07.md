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
The jank isn't a React 18 bug—you've hit a **context value object reference problem**. Here's what's actually happening:

## The Root Cause

Every time `Dashboard` renders, the context value is a **new object**:

```tsx
value={{ user, settings, searchQuery, setSearchQuery }}  // NEW OBJECT EVERY RENDER
```

Even though `user` and `settings` haven't changed, the object reference is different. **All context consumers re-render on object reference change**, regardless of whether the values they actually use changed.

## Why Your Fixes Didn't Work

- **React.memo on children**: The child is re-rendering because its *parent* (`Dashboard`) re-renders when the context value object changes. Memo can't help.
- **useMemo for the JSX**: The JSX doesn't get recreated, but `Dashboard` still re-renders, re-evaluating the context.

---

## The Fix: Memoize the Context Value

Wrap the context value in `useMemo`:

```tsx
export function AppProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchUser().then(setUser);
    fetchSettings().then(setSettings);
  }, []);

  // Memoize the context value to prevent recreating the object
  const value = useMemo(
    () => ({ user, settings, searchQuery, setSearchQuery }),
    [user, settings, searchQuery]
  );

  return (
    <AppContext.Provider value={value}>
      {children}
    </AppContext.Provider>
  );
}
```

**Why this works**: Now the context value object only changes when one of its dependencies (`user`, `settings`, `searchQuery`) actually changes. When only `searchQuery` changes, only consumers of `searchQuery` re-render.

---

## Better: Split Contexts by Concern

For maximum efficiency, split into separate contexts so components only subscribe to what they need:

```tsx
const UserContext = createContext<User | null>(null);
const SettingsContext = createContext<Settings>(defaultSettings);
const SearchContext = createContext<{ query: string; setQuery: (q: string) => void }>({ query: '', setQuery: () => {} });

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchUser().then(setUser);
    fetchSettings().then(setSettings);
  }, []);

  const searchValue = useMemo(() => ({ query: searchQuery, setQuery: setSearchQuery }), [searchQuery]);

  return (
    <UserContext.Provider value={user}>
      <SettingsContext.Provider value={settings}>
        <SearchContext.Provider value={searchValue}>
          {children}
        </SearchContext.Provider>
      </SettingsContext.Provider>
    </UserContext.Provider>
  );
}
```

Now:
- `UserProfile` only re-renders if `user` changes
- `SettingsPanel` only re-renders if `settings` changes
- `SearchResults` only re-renders if `searchQuery` changes

---

## Why You Don't Need Zustand

Zustand is great for other reasons (DevTools, persistence, async middleware), but **this performance problem has nothing to do with context being slow**. It's a pattern issue. The `useMemo` fix will eliminate the jank completely.

**Before rewriting 40 components**, try the `useMemo` fix first—it should resolve your profiler results immediately. If you want to pursue Zustand later for architectural reasons, that's fine, but it's not necessary here.

## Response B
Working through the checklist:

**1. What am I assuming?**
- That "React.memo is broken" is a misdiagnosis (pattern-matching bias)
- That context value instability is the root cause
- That you're interpreting React DevTools correctly

**2. What evidence do I have?**
- Your code snapshot (read, not verified against React behavior)
- General understanding of React 18 context (medium confidence — not checked against React 18 specifics in this session)
- You've stated the symptom, but I haven't seen the actual React DevTools output

**3. What would change my mind?**
- If wrapping the context value in useMemo still doesn't fix it
- If you show me that `user` and `settings` objects ARE actually changing on every keystroke
- If splitting the context into separate providers still causes re-renders

**4. The cost of being wrong?**
- **Very high.** You're considering rewriting all state management. Wrong diagnosis = wasted days.

---

## The Actual Problem (High Confidence)

Your issue is **not** that React.memo is broken. It's that **your context value object is unstable**, and this is likely preventing memo from working the way you expect.

Here's why:

```tsx
return (
  <AppContext.Provider value={{ user, settings, searchQuery, setSearchQuery }}>
    {children}
  </AppContext.Provider>
);
```

Every render, you create a **new object literal**. Even if `user` and `settings` are the same references, the object `{ user, settings, searchQuery, setSearchQuery }` is **always new**.

React's context algorithm: when the provider value changes by reference, **all consumers re-render**. This is correct behavior — but it's cascading through your tree because Dashboard itself consumes this context.

**Why React.memo didn't help:** React.memo compares props, but Dashboard (which consumes context) still re-renders because the context value changed. Even though UserProfile receives stable props, there's a subtlety: the context-driven re-render of Dashboard can interfere with memo's ability to bail out, depending on how the tree reconciles.

---

## The Fix (Test This First — Don't Rewrite)

Wrap the context value in `useMemo` **keyed only to values that actually change**:

```tsx
const contextValue = useMemo(
  () => ({ user, settings, searchQuery, setSearchQuery }),
  [user, settings, searchQuery, setSearchQuery]
);

return (
  <AppContext.Provider value={contextValue}>
    {children}
  </AppContext.Provider>
);
```

**But this still won't fully solve it** if all four dependencies change. The real fix is to **split your context**:

```tsx
// 1. Static data context (re-renders only when user or settings fetch)
const StaticDataContext = createContext<{ user: User | null; settings: Settings } | null>(null);

// 2. Search context (can change rapidly without affecting other subscribers)
const SearchContext = createContext<{ searchQuery: string; setSearchQuery: (q: string) => void } | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchUser().then(setUser);
    fetchSettings().then(setSettings);
  }, []);

  const staticData = useMemo(() => ({ user, settings }), [user, settings]);
  const search = useMemo(() => ({ searchQuery, setSearchQuery }), [searchQuery, setSearchQuery]);

  return (
    <StaticDataContext.Provider value={staticData}>
      <SearchContext.Provider value={search}>
        {children}
      </SearchContext.Provider>
    </StaticDataContext.Provider>
  );
}
```

Now:
- **UserProfile and SettingsPanel** consume StaticDataContext — they only re-render when actual data changes (rarely)
- **SearchResults** consumes SearchContext — it re-renders on keystroke (expected)
- Dashboard can consume just SearchContext for the input, avoiding the full context change cascade

---

## Before You Rewrite Everything

**Test this hypothesis:**
1. Add `console.log()` before your context value creation to count re-renders
2. Add a `key` prop to UserProfile with some id — if it's re-mounting vs re-rendering, the key will tell you
3. Split the context as above and measure re-renders again
4. Check React DevTools Profiler: does it show SearchResults re-rendering (expected) or UserProfile (unexpected)?

If splitting the context fixes it, your tech lead's Zustand suggestion was the wrong fix for the right symptom. If splitting *doesn't* fix it, something else is happening (likely the user/settings are being recreated).

---

**What's your confidence the user and settings objects stay the same reference across renders?** That's the next thing to verify. Can you add a console.log showing their identity before/after a keystroke?

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
