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