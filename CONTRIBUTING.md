# Contributing Guide

How to contribute to the Trader project.

---

## Development Setup

```bash
# Clone and setup
git clone https://github.com/MrLion/trader.git
cd trader
./setup.sh

# Install dev dependencies
make install-dev

# Verify
make test
```

---

## Code Style

### Python Formatting

We use **Black** and **isort** for formatting:

```bash
# Format code
make format

# Check linting
make lint
```

Pre-commit hooks enforce this automatically.

### Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Functions | `snake_case` | `calculate_stage2_score` |
| Classes | `PascalCase` | `AlpacaClient` |
| Constants | `UPPER_SNAKE` | `MAX_POSITIONS` |
| Private | `_leading_underscore` | `_internal_helper` |
| Test files | `test_{module}_{feature}.py` | `test_rate_limiter.py` |

### Docstrings

Use concise one-line docstrings for simple functions. Only add multi-line docstrings when behavior is non-obvious.

```python
def calculate_risk(entry, stop, shares):
    """Calculate dollar risk for a position."""
    return (entry - stop) * shares
```

---

## Commit Messages

Use **Conventional Commits**:

```
<type>: <subject>

[optional body]
```

### Types

| Type | Use For |
|------|---------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `test` | Adding tests |
| `refactor` | Code change with no behavior change |
| `chore` | Build/config/tooling changes |

### Examples

```
feat: add --top flag to sector scan

fix: resolve NaN propagation in VCP stop calc

docs: update README with new script references

test: add coverage for partial fill recovery

refactor: simplify entry score calculation
```

---

## Pull Request Process

1. **Branch naming:**
   - Features: `feat/description`
   - Fixes: `fix/description`
   - Docs: `docs/description`

2. **Before submitting:**
   ```bash
   make test        # All tests pass
   make lint        # No lint errors
   make format      # Code formatted
   ```

3. **PR description:**
   - What changed
   - Why it changed
   - How to test
   - Link to related issue (if any)

4. **Review checklist:**
   - [ ] Tests added/updated
   - [ ] Documentation updated
   - [ ] CHANGELOG.md updated
   - [ ] Version bumped (if applicable)
   - [ ] No breaking changes (or documented)

---

## Versioning

The project uses a 4-digit format: `0.XX.YY.ZZ`

| Position | Meaning | When to Bump |
|----------|---------|--------------|
| `XX` | Major milestone | Breaking changes, architecture shifts |
| `YY` | Features | New functionality, enhancements |
| `ZZ` | Fixes | Bug fixes, corrections |

**Process:**
1. Update `VERSION` file
2. Update `CHANGELOG.md`
3. Commit: `chore: bump version to X.X.X.X`
4. Create git tag: `git tag vX.X.X.X`
5. Push tag: `git push origin vX.X.X.X`

---

## Documentation Rules

- Update docs when adding/modifying features
- Follow ATX headers (`## Heading`)
- Use code blocks with language tags
- Use tables for structured data
- Keep internal notes in `TOOLS.md`, user docs in `docs/`

---

## Related

- [DEVELOPMENT.md](DEVELOPMENT.md) — Development setup
- [ARCHITECTURE.md](ARCHITECTURE.md) — System design
- [CHANGELOG.md](../CHANGELOG.md) — Release history
