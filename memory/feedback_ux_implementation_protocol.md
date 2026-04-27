---
name: Implementation Protocol - Ask Before Changes
description: Never implement without explicit approval - user must approve all code changes
type: feedback
---

**Rule:** Never write, edit, or modify code without explicit user approval.

**Why:** 2026-04-17 session - Assistant made multiple code changes to trend_screener.py after user asked for mockups only. User had to revert work and redo changes. Repeated violations of "ask before changes" instruction caused significant wasted time.

**How to apply:** 
- Mockups/proposals = text output only, no tool calls
- Implementation = explicit user approval required ("Want me to implement this?")
- When user says "show me" = they want to SEE, not have code written
- Default: wait for "implement this" or equivalent before any Edit/Write
