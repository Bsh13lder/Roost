"""LLM domain: the ``Model`` protocol and its event types (``types.py``),
model-id registry + factory (``registry.py``), the deterministic
``ScriptedModel`` used by every test and ``ROOST_MODEL=scripted``
(``scripted.py``), and the real Claude Agent SDK provider with its
always-on, default-deny ``ClaudeAgentOptions`` (``claude_sdk.py``) — see
``docs/specs/2026-10-12-roost-design.md`` and the Night-1 shared
contract's "LLM" section.

Nothing in this package imports ``roost.talk`` or ``roost.desk``: the
model layer only ever produces/consumes ``ModelEvent``s, never calls a
tool itself. That boundary is enforced by ``tests/test_claude_sdk_options.py``.
"""
