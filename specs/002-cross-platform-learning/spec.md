# Feature Spec: Cross-Session Memory + Cursor Adapter Hardening

**Feature Branch**: `[002-cross-platform-learning]`  
**Created**: 2026-01-29  
**Input**: User description: "Phase 2 items 2.1 and 2.2 (cross-session learning + Cursor adapter), move 2.3/2.4 to advanced features"

## Problem Statement

Cross-session memory works conceptually, but the system does not deterministically filter and rank learnings by project + confidence using the memory index, making results inconsistent and hard to test. Cursor ingestion exists but is not clearly wired to connected paths, and docs still show Cursor/Cline as planned. There is no adapter contribution guide for adding new platforms. Phase 2 also includes cross-platform learning transfer and a feedback loop that should be deferred to advanced features.

## Goals

- Provide a deterministic memory prefilter (FTS + confidence + project scope) for memory search/chat usage.
- Ensure Cursor session ingestion works from connected/custom paths and can surface chat content.
- Document how to add a new platform adapter.
- Update Phase 2 docs to remove 2.3/2.4 and move them to advanced features.

## Non-goals

- Implement cross-platform learning transfer (2.3).
- Implement learning feedback loop (2.4).
- Auto-inject memory into sessions.
- Add integration tests that hit external APIs.

## Primary User Flow (Happy Path)

1. User connects Cursor (`acreta connect cursor [--path ...]`).
2. Indexer scans connected paths and indexes Cursor sessions.
3. In a new session, agent runs `acreta memory search "..."` or `acreta chat "Create a concise project summary for ."`.
4. Acreta filters learnings by project + confidence, ranks by FTS match + confidence, and returns a concise response.

## User Stories (prioritized)

### P1 — Cross-session memory retrieval

As an agent/user, I can request memory search or chat-based project summary and receive relevant learnings scoped to the current project and confidence threshold.

**Acceptance Scenarios**:
1. **Given** a learning tagged to the current repo with confidence >= 0.7, **When** I query memory with a matching keyword, **Then** the learning is included in results.
2. **Given** a learning below the confidence threshold or for a different project, **When** I run memory search or a chat-based project summary request, **Then** it is excluded.
3. **Given** no matching learnings, **When** I query memory, **Then** the response clearly states that no relevant learnings were found.

### P1 — Cursor sessions are ingestible from connected paths

As a user, I can connect a Cursor trace directory and have Cursor sessions indexed and viewable.

**Acceptance Scenarios**:
1. **Given** a Cursor `state.vscdb` containing `composerData:` and `bubbleId:` entries, **When** sessions are analyzed, **Then** both session IDs appear in results with messages.
2. **Given** a connected custom Cursor path, **When** indexing runs, **Then** sessions from that path are indexed.

### P2 — Adapter contribution guide

As a contributor, I can follow a guide to add a new adapter that matches the ingestion interface and tests.

**Acceptance Scenarios**:
1. **Given** the adapter guide, **When** I follow it, **Then** I can add a new ingestion module, tests, and docs without guessing required functions.

## Requirements

### Functional

- **FR-001**: Memory search/chat requests must prefilter learnings by project context and `confidence >= 0.7`.
- **FR-002**: Prefiltered learnings must be ranked by FTS relevance and then confidence.
- **FR-003**: Indexing must honor connected platform paths from `~/.acreta/platforms.json`.
- **FR-004**: Cursor adapter must parse both `composerData:` and `bubbleId:` entries and surface chat messages.
- **FR-005**: Provide adapter contribution documentation in `docs/`.

### Non-functional

- **NFR-001**: No network calls for memory prefiltering; use local storage only.
- **NFR-002**: Unit tests cover prefiltering behavior and cursor indexing from custom paths.

## Edge Cases

- Query string contains symbols that break FTS parsing.
- No learnings exist in the store.
- Cursor DB is missing or locked; analysis should skip safely.
- Project context is missing; fallback should still return top results by relevance.

## Success Criteria (measurable)

- **SC-001**: Unit tests pass for memory prefiltering and cursor indexing from connected paths.
- **SC-002**: Phase 2 docs no longer include 2.3/2.4 and advanced features include them.

## Assumptions

- Memory search/chat continues to use the agent for response formatting, but uses a deterministic prefilter.
- Cross-platform learning transfer and feedback loop are deferred to advanced features.

## Open Questions

- None.
