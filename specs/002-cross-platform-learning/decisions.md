# Decisions: Cross-Session Memory + Cursor Adapter Hardening

**Feature Branch**: `[002-cross-platform-learning]`  
**Created**: 2026-01-29

## ADR-001: Prefilter learnings with local FTS before agent response

**Status**: Accepted  
**Date**: 2026-01-29

### Context

Cross-session memory currently relies on the agent to grep/read files, which is non-deterministic and hard to test. Phase 2 requires project + confidence filtering and FTS relevance ranking.

### Options Considered

1. Keep agent-only search (grep/glob) and rely on prompt instructions.
2. Prefilter learnings using the local FTS index + confidence, then pass results to the agent.

### Decision

We choose **Option 2** because it provides deterministic filtering and ranking, enables unit tests, and still preserves agent-driven summarization.

### Consequences

**Positive:**
- Deterministic filtering/ranking with local storage.
- Tests can assert results without external APIs.

**Negative:**
- Adds an indexing step before queries.
