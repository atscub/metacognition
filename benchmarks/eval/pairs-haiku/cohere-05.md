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
## Discrepancies Found

I've systematically checked all three artifacts against the 10 coherence categories. Here are the **critical inconsistencies**:

### 🔴 **CRITICAL: Missing `role` Field**
- **Frontend queries:** `role` on User type
- **Schema defines:** No `role` field exists
- **Impact:** This query will fail at runtime with GraphQL validation error
- **Location:** Frontend component, line ~23 in the USER_PROFILE_QUERY

### 🔴 **CRITICAL: Avatar Field Mapping Broken**
- **Schema:** Defines `avatar: String` on User type
- **Resolver (createPost/updateUser):** Updates `profile_image` column, not `avatar`
- **No mapping resolver:** User type has no resolver to map `profile_image` → `avatar`
- **Impact:** Avatar will be `null` or undefined when queried, even though data exists in database
- **Location:** Resolver updateUser, line ~48; schema User type, line ~13

### 🔴 **HIGH: Comments Return Type Violation**
- **Schema:** `comments: [Comment!]!` — non-null list guarantee
- **Resolver:** `return comments.length > 0 ? comments : null` — returns `null`
- **Impact:** Violates GraphQL contract, breaks client type safety
- **Location:** Resolver Post.comments, line ~73

### 🟡 **MEDIUM: Inconsistent Avatar Naming Pattern**
- All other fields follow `camelCase (schema) ↔ snake_case (database)` pattern
- **Exception:** `avatar` ↔ `profile_image` — completely different names
- **Breaks:** Implicit field mapping conventions
- **Should be:** Both `avatar` or acknowledge the semantic difference

### 🟡 **MEDIUM: Misleading `feed` Query Name**
- **Name suggests:** A social feed (posts the user would see)
- **Actually returns:** Only posts authored by that userId
- **Correct name:** `userPosts` (reflects actual semantics)
- **Note:** Frontend uses it correctly, but the API contract is imprecisely named

---

## Quick Fixes Needed

1. **Remove `role` from frontend query** OR **add `role: String` to User schema**
2. **Add User field resolver** to map `profile_image` → `avatar`
3. **Fix Post.comments** to return `[]` instead of `null`
4. **Rename `feed`** to `userPosts` or change resolver to return actual social feed
5. **Standardize avatar column** name (use `avatar` consistently)

## Response B
# Consistency Review

Found **4 discrepancies** between the artifacts:

## 1. **Missing Schema Field: `user.role`** ⚠️ **Critical**
- **Frontend queries**: `user.role` in UserProfile component
- **Schema defines**: No `role` field in User type
- **Impact**: GraphQL will reject this query with "Cannot query field 'role' on type 'User'"
- **Fix**: Add `role: String` to User type in schema, or remove from frontend query

## 2. **Post.comments Nullability Violation** ⚠️ **Critical**
- **Schema defines**: `comments: [Comment!]!` (non-nullable list)
- **Resolver returns**: `null` when comments.length is 0
  ```javascript
  return comments.length > 0 ? comments : null;  // ← violates schema
  ```
- **Impact**: Breaks schema contract; should return empty array `[]` instead
- **Fix**: Change to `return comments || []`

## 3. **Feed Query Semantics Mismatch**
- **Schema intent**: Appears to be a generic "feed" query
- **Resolver implementation**: Returns posts WHERE `author_id: userId` (user's own posts only)
- **Frontend expectation**: Uses it to show "Recent Posts" from the user
- **Issue**: "Feed" typically means posts from followed users, not a user's own posts. Consider renaming to `userPosts` for clarity, or document the actual behavior

## 4. **Pagination Inconsistency**
- **users query**: Supports pagination with `limit` + `offset` and returns paginated `UserConnection`
- **feed query**: Accepts `limit` but no `offset` parameter (no pagination support)
- **Impact**: Frontend can only fetch the first N posts from a feed, can't get more without refetching
- **Fix**: Add `offset: Int = 0` parameter to feed query, or return a paginated type like `PostConnection`

---

**Priority fixes**: #1 and #2 will cause runtime errors. #3 and #4 are design consistency issues.

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
