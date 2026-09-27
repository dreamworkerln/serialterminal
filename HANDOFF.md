# Chatter handoff pointer

The authoritative handoff for the RadioConnect / Echo / Chatter / Chatter ACK workstream does **not** live in this source branch.

Go to:

```text
dev_handoff
```

and recover context in this order:

```text
1. CONTEXT.md, if present
2. HANDOFF_INDEX.md
3. the latest HANDOFF_NNN.md named by the index
4. KNOWLEDGE_BASE_POLICY.md
5. relevant notes/
6. refetch the actual source branch before code work
```

Rules for future handoff work:

```text
- do not turn this file into a second full handoff;
- full recovery snapshots are append-only on dev_handoff;
- create the next HANDOFF_NNN.md there, verify it, then advance HANDOFF_INDEX.md;
- use CONTEXT.md there as the mutable write-ahead/recovery journal for substantial multi-step work;
- refetch current branch HEAD before making implementation claims or writes;
- dev_handoff is a separate SACK handoff and must not be used for this workstream.
```

This branch remains the source-code authority for the current non-reliable componentized Chatter implementation. Project-local documentation such as `STATIC_ANALYSIS.md` belongs here and is separate from the handoff mechanism.
