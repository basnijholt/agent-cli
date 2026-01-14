# Examples: Parallel Agent Workflows

Real-world scenarios for spawning parallel AI coding agents.

## Scenario 1: Multi-feature implementation

**User request**: "Implement user auth, payment processing, and email notifications"

**Strategy**: Three independent features → spawn three agents.

```bash
agent-cli dev new auth-feature --agent --prompt "Implement JWT-based user authentication.

Context:
- Backend is FastAPI in src/api/
- Use existing User model in src/models/user.py
- Follow patterns in existing endpoints (see src/api/routes/)
- Store JWT secret in environment variable JWT_SECRET

Requirements:
- POST /auth/register - create new user
- POST /auth/login - return JWT token
- GET /auth/me - return current user (requires auth)
- Add auth dependency for protected routes

When complete, write a summary to .claude/REPORT.md including:
- What you implemented
- Key decisions you made
- Any questions or concerns for review"

agent-cli dev new payment-integration --agent --prompt "Integrate Stripe payment processing.

Context:
- Backend is FastAPI in src/api/
- Use stripe Python package
- Store STRIPE_SECRET_KEY in environment

Requirements:
- POST /payments/create-intent - create payment intent
- POST /payments/webhook - handle Stripe webhooks
- Add Payment model to track transactions

When complete, write a summary to .claude/REPORT.md including:
- What you implemented
- Key decisions you made
- Any questions or concerns for review"

agent-cli dev new email-notifications --agent --prompt "Implement email notification system.

Context:
- Backend is FastAPI in src/api/
- Use a simple email library (suggest one appropriate for the stack)
- Store SMTP settings in environment

Requirements:
- Background task for sending emails
- Email templates for: welcome, password reset, order confirmation
- POST /notifications/send-test - for testing

When complete, write a summary to .claude/REPORT.md including:
- What you implemented
- Key decisions you made
- Any questions or concerns for review"
```

## Scenario 2: Test-driven development

**User request**: "Add a caching layer with comprehensive tests"

**Strategy**: One agent writes tests first, another implements.

```bash
agent-cli dev new cache-tests --agent --prompt "Write comprehensive tests for a caching layer.

The caching system should support:
- get(key) -> value or None
- set(key, value, ttl_seconds=None)
- delete(key)
- clear()
- Support for Redis backend and in-memory fallback

Write tests in tests/test_cache.py using pytest. Tests should cover:
- Basic get/set/delete operations
- TTL expiration
- Cache miss behavior
- Backend switching

Do NOT implement the cache itself - only write tests.

When complete, write a summary to .claude/REPORT.md including:
- Test cases covered
- Edge cases considered
- Suggested interface for implementation"
```

After reviewing the tests:

```bash
agent-cli dev new cache-impl --from cache-tests --agent --prompt "Implement the caching layer to pass existing tests.

Tests are in tests/test_cache.py - read them first to understand the interface.

Implement in src/cache.py:
- CacheBackend abstract base class
- RedisBackend implementation
- MemoryBackend implementation
- Cache facade that uses configured backend

When complete, write a summary to .claude/REPORT.md including:
- Implementation approach
- Any deviations from test expectations
- Performance considerations"
```

## Scenario 3: Large refactoring by module

**User request**: "Refactor the API to use consistent error handling"

**Strategy**: Split by module, each agent handles one area.

```bash
agent-cli dev new refactor-users-errors --agent --prompt "Refactor error handling in the users module.

Current state: Inconsistent error responses across src/api/routes/users.py

Target pattern:
- Use HTTPException with structured detail: {'error': 'code', 'message': 'Human readable'}
- Error codes: USER_NOT_FOUND, USER_EXISTS, INVALID_CREDENTIALS, etc.
- Log errors with context before raising

Only modify files in src/api/routes/users.py and related user logic.

When complete, write a summary to .claude/REPORT.md including:
- Files changed
- Error codes introduced
- Any breaking changes to API responses"

agent-cli dev new refactor-orders-errors --agent --prompt "Refactor error handling in the orders module.

Current state: Inconsistent error responses across src/api/routes/orders.py

Target pattern:
- Use HTTPException with structured detail: {'error': 'code', 'message': 'Human readable'}
- Error codes: ORDER_NOT_FOUND, INVALID_STATUS, PAYMENT_REQUIRED, etc.
- Log errors with context before raising

Only modify files in src/api/routes/orders.py and related order logic.

When complete, write a summary to .claude/REPORT.md including:
- Files changed
- Error codes introduced
- Any breaking changes to API responses"
```

## Scenario 4: Documentation and implementation in parallel

**User request**: "Add a plugin system with documentation"

**Strategy**: One agent implements, another writes docs simultaneously.

```bash
agent-cli dev new plugin-system --agent --prompt "Implement a plugin system.

Requirements:
- Plugin base class with lifecycle hooks: on_load, on_unload, on_event
- Plugin registry for discovery and management
- Load plugins from a plugins/ directory
- Example plugin demonstrating the interface

Implement in src/plugins/

When complete, write a summary to .claude/REPORT.md including:
- Architecture decisions
- Plugin interface details
- Example usage"

agent-cli dev new plugin-docs --agent --prompt "Write documentation for the plugin system.

Note: Implementation is happening in parallel in another branch.
Write documentation based on a typical plugin system design:
- Plugin base class with on_load, on_unload, on_event hooks
- Plugin registry pattern
- Plugins loaded from plugins/ directory

Create:
- docs/plugins/overview.md - high-level concepts
- docs/plugins/creating-plugins.md - step-by-step guide
- docs/plugins/api-reference.md - detailed API docs

When complete, write a summary to .claude/REPORT.md including:
- Documentation structure
- Any assumptions made about the implementation
- Suggestions for the implementation based on documentation needs"
```

## Reviewing results

After agents complete their work:

```bash
# Check status of all worktrees
agent-cli dev status

# Read reports from each agent
agent-cli dev run auth-feature cat .claude/REPORT.md
agent-cli dev run payment-integration cat .claude/REPORT.md
agent-cli dev run email-notifications cat .claude/REPORT.md

# Open a worktree to review code
agent-cli dev editor auth-feature

# Clean up after merging
agent-cli dev clean --merged
```
