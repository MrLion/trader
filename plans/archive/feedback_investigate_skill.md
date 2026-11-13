---
name: Investigation Skill Protocol
description: When /investigate is invoked, do not implement - only report findings and wait for approval
type: feedback
originSessionId: 3094223a-e0af-4b05-83bf-eb2b3409f321
---
When user invokes `/investigate` skill:

1. INVESTIGATE ONLY - Do not write any code changes
2. Report root cause, evidence, and recommended fix
3. Create proposition with file:line references
4. **Explicitly ask**: "Want me to implement this fix?"
5. **WAIT for explicit "yes"** before any Edit/Write tools

**Why:** Investigation and implementation are separate phases. User may want to review findings before proceeding, or the investigation may reveal the fix should be handled differently.

**How to apply:** After reporting findings, end response with "Want me to implement this fix?" and stop. Do not proceed with edits until user confirms.