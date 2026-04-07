# Task: cohere-05 — GraphQL schema vs resolver vs client query

## Prompt
Review the following three artifacts for consistency. Identify any discrepancies between them.

## Artifact 1: GraphQL Schema (schema.graphql)

```graphql
type Query {
  user(id: ID!): User
  users(limit: Int = 20, offset: Int = 0): UserConnection!
  post(id: ID!): Post
  feed(userId: ID!, limit: Int = 10): [Post!]!
}

type Mutation {
  createPost(input: CreatePostInput!): Post!
  updateUser(id: ID!, input: UpdateUserInput!): User!
}

type User {
  id: ID!
  username: String!
  displayName: String!
  email: String!
  avatar: String
  bio: String
  postCount: Int!
  createdAt: DateTime!
}

type Post {
  id: ID!
  title: String!
  body: String!
  author: User!
  tags: [String!]!
  comments: [Comment!]!
  likeCount: Int!
  createdAt: DateTime!
  updatedAt: DateTime!
}

type Comment {
  id: ID!
  body: String!
  author: User!
  createdAt: DateTime!
}

type UserConnection {
  nodes: [User!]!
  totalCount: Int!
  hasNextPage: Boolean!
}

input CreatePostInput {
  title: String!
  body: String!
  tags: [String!]
}

input UpdateUserInput {
  displayName: String
  bio: String
  avatar: String
}

scalar DateTime
```

## Artifact 2: Resolvers (src/resolvers/index.js)

```javascript
const { db } = require('../database');
const { AuthenticationError } = require('apollo-server-express');

const resolvers = {
  Query: {
    user: async (_, { id }) => {
      return db('users').where({ id }).first();
    },
    users: async (_, { limit, offset }) => {
      const nodes = await db('users').limit(limit).offset(offset);
      const [{ count }] = await db('users').count('* as count');
      return {
        nodes,
        totalCount: parseInt(count),
        hasNextPage: offset + limit < parseInt(count),
      };
    },
    post: async (_, { id }) => {
      return db('posts').where({ id }).first();
    },
    feed: async (_, { userId, limit }) => {
      return db('posts')
        .where({ author_id: userId })
        .orderBy('created_at', 'desc')
        .limit(limit);
    },
  },

  Mutation: {
    createPost: async (_, { input }, context) => {
      if (!context.user) throw new AuthenticationError('Must be logged in');
      const [post] = await db('posts')
        .insert({
          title: input.title,
          body: input.body,
          tags: JSON.stringify(input.tags || []),
          author_id: context.user.id,
        })
        .returning('*');
      return post;
    },
    updateUser: async (_, { id, input }, context) => {
      if (!context.user || context.user.id !== id) {
        throw new AuthenticationError('Not authorized');
      }
      const [user] = await db('users')
        .where({ id })
        .update({
          display_name: input.displayName,
          bio: input.bio,
          profile_image: input.avatar,
        })
        .returning('*');
      return user;
    },
  },

  User: {
    displayName: (user) => user.display_name,
    postCount: async (user) => {
      const [{ count }] = await db('posts')
        .where({ author_id: user.id })
        .count('* as count');
      return parseInt(count);
    },
    createdAt: (user) => user.created_at,
  },

  Post: {
    author: async (post) => {
      return db('users').where({ id: post.author_id }).first();
    },
    tags: (post) => {
      return typeof post.tags === 'string' ? JSON.parse(post.tags) : post.tags;
    },
    comments: async (post) => {
      const comments = await db('comments').where({ post_id: post.id });
      return comments.length > 0 ? comments : null;
    },
    likeCount: async (post) => {
      const [{ count }] = await db('likes')
        .where({ post_id: post.id })
        .count('* as count');
      return parseInt(count);
    },
    createdAt: (post) => post.created_at,
    updatedAt: (post) => post.updated_at,
  },

  Comment: {
    author: async (comment) => {
      return db('users').where({ id: comment.author_id }).first();
    },
    createdAt: (comment) => comment.created_at,
  },
};

module.exports = resolvers;
```

## Artifact 3: Frontend Component (src/components/UserProfile.tsx)

```tsx
import React from 'react';
import { useQuery, gql } from '@apollo/client';
import { PostCard } from './PostCard';
import { Avatar } from './Avatar';
import { Spinner } from './Spinner';

const USER_PROFILE_QUERY = gql`
  query UserProfile($userId: ID!) {
    user(id: $userId) {
      id
      username
      displayName
      email
      avatar
      bio
      role
      postCount
      createdAt
    }
    feed(userId: $userId, limit: 5) {
      id
      title
      body
      tags
      likeCount
      createdAt
      author {
        id
        username
        avatar
      }
      comments {
        id
        body
        author {
          id
          username
        }
        createdAt
      }
    }
  }
`;

interface UserProfileProps {
  userId: string;
}

export function UserProfile({ userId }: UserProfileProps) {
  const { data, loading, error } = useQuery(USER_PROFILE_QUERY, {
    variables: { userId },
  });

  if (loading) return <Spinner />;
  if (error) return <div className="error">Failed to load profile</div>;

  const { user, feed } = data;

  return (
    <div className="profile-page">
      <header className="profile-header">
        <Avatar src={user.avatar} alt={user.displayName} size="lg" />
        <div className="profile-info">
          <h1>{user.displayName}</h1>
          <span className="username">@{user.username}</span>
          {user.role && (
            <span className="role-badge">{user.role}</span>
          )}
          {user.bio && <p className="bio">{user.bio}</p>}
          <span className="post-count">{user.postCount} posts</span>
        </div>
      </header>
      <section className="recent-posts">
        <h2>Recent Posts</h2>
        {feed.map((post: any) => (
          <PostCard key={post.id} post={post} />
        ))}
      </section>
    </div>
  );
}
```


## Response A
## Coherence Audit: GraphQL Schema, Resolvers, Frontend Component

Working through all 10 categories, comparing each artifact against the other two.

---

### 1. Factual Accuracy — 3 findings

**Finding A (High): `role` field queried but not defined**

The frontend queries `role` on `User`:
```graphql
# UserProfile.tsx
user { ..., role, ... }
```
The schema has no `role` field on `User`. This query will fail or return `null`/error at runtime. The component also conditionally renders a `<span className="role-badge">` on it — dead UI.

---

**Finding B (High): `Post.comments` nullability violation**

Schema declares comments as non-nullable list with non-nullable items:
```graphql
comments: [Comment!]!   # can never be null; always returns a list
```
Resolver returns `null` when there are no comments:
```javascript
return comments.length > 0 ? comments : null;  // violates [Comment!]!
```
Should return `[]`. This will cause a GraphQL runtime error for any post with zero comments.

---

**Finding C (High): `avatar` / `profile_image` column mismatch**

`updateUser` writes `input.avatar` to the DB column `profile_image`:
```javascript
.update({ display_name: input.displayName, bio: input.bio, profile_image: input.avatar })
```
But the `User` resolver block has no field resolver for `avatar`. Default resolution will look for `user.avatar` on the raw DB row. If the DB column is `profile_image` (as the update implies), `user.avatar` will always be `undefined` — writes succeed but reads return nothing. The frontend queries `avatar` on both `user` and post `author`, so this breaks avatar display site-wide.

---

### 2. Representational Completeness — 1 finding

**Finding D (Low): `createPost` mutation has no frontend representation**

`createPost` exists in both the schema and resolvers but the frontend component doesn't surface it. Not necessarily a bug — it may live in another component — but worth noting for a completeness audit.

---

### 3. Voice Consistency — Clean

All three artifacts are consistent in their technical register. N/A for prose voice.

---

### 4. Naming Coherence — 1 finding

**Finding E (Medium): `feed` describes user's own posts, not a feed**

The resolver filters by `author_id: userId`, returning a user's *own* posts:
```javascript
feed: async (_, { userId, limit }) => {
  return db('posts').where({ author_id: userId })...
```
A "feed" conventionally means posts from followed users or a timeline of others' content. The frontend's own section header agrees with the resolver's *behavior* ("Recent Posts") but the query name `feed` misrepresents it. This naming mismatch will confuse anyone implementing a real feed later, and the frontend component reinforces the confusion by using the `feed` query to populate "Recent Posts."

---

### 5. Framing Precision — same as Finding E above

`feed` is scoped narrower than its name implies.

---

### 6–10. (Origin Fidelity, Tone, Category Accuracy, Redundancy, Scope Discipline) — Clean

No findings in these categories for code artifacts of this type.

---

## Summary Table

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| A | **High** | Schema ↔ Frontend | `role` field queried in component, not in schema |
| B | **High** | Schema ↔ Resolvers | `comments: [Comment!]!` can never be null per schema; resolver returns `null` for empty lists |
| C | **High** | Resolvers (write vs. read path) | `avatar` written to `profile_image` DB column; no resolver maps it back; reads always return undefined |
| D | Low | Schema/Resolvers ↔ Frontend | `createPost` mutation has no frontend counterpart (may be in another component) |
| E | **Medium** | All three | `feed` field name implies social timeline; behavior is user's own posts; frontend label ("Recent Posts") agrees with behavior but not the query name |

---

**Priority fixes:** A and B are runtime errors (will crash). C is a silent data bug (saves succeed, reads silently fail). E is a semantic debt that will cause confusion when a real feed is needed.

## Response B
Three discrepancies found:

---

**1. `role` field queried by frontend but absent from schema**

`UserProfile.tsx` queries `role` on `User` and renders a badge for it. The schema's `User` type has no `role` field. This will fail GraphQL validation at query time.

---

**2. `Post.comments` resolver returns `null` on empty list, violating schema**

Schema declares `comments: [Comment!]!` — the field itself is non-nullable (the `!` after `]`).

The resolver does:
```js
return comments.length > 0 ? comments : null;  // ← returns null
```

Returning `null` for a non-nullable field causes a GraphQL runtime error that nulls out the parent `Post`. It should return `[]` for the empty case.

---

**3. `avatar` stored as `profile_image` in DB but no field resolver maps it back**

In `updateUser`, the resolver writes:
```js
profile_image: input.avatar,
```

But the `User` field resolvers only map `display_name → displayName` and `created_at → createdAt`. There's no resolver for `avatar`, so Apollo falls back to reading `user.avatar` from the raw DB row — which is always `undefined` since the column is named `profile_image`. Every user's avatar will silently return `null`.

Fix: add to the `User` resolver block:
```js
avatar: (user) => user.profile_image,
```

---

**Summary table**

| # | Location | Field | Issue |
|---|----------|-------|-------|
| 1 | Frontend query | `User.role` | Field doesn't exist in schema |
| 2 | Resolver `Post.comments` | return value | Returns `null` for non-nullable `[Comment!]!` |
| 3 | Resolver `User` | `avatar` | No mapping from `profile_image` DB column |

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
