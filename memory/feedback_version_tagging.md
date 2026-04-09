---
name: Version Tagging Discipline
description: Always create git tags when updating CHANGELOG version bumps
type: feedback
---

**Rule:** When updating CHANGELOG with version bumps (e.g., v0.2.2), always create corresponding git tags immediately.

**Why:** The CHANGELOG version numbers are just documentation without tags. Tags make versions actionable rollback points. This is critical for a trading engine where a bad deploy could lose real money.

**How to apply:**
1. After updating CHANGELOG.md with a new version entry
2. Run: `git tag v0.2.2 && git push origin v0.2.2`
3. Verify with: `git tag -l` and `git ls-remote --tags origin`

**Example discovered:** v0.2.2 was in CHANGELOG but no git tag existed, making rollback impossible if the paper trading engine went live with bugs.
