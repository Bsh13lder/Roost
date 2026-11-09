"""Talk domain: the encrypted threads/messages store (``TalkStore``) and
its ``thread_out``/``message_out`` serializers, plus the model-facing
side Task 11 adds — ``instructions.py`` (the bot's system prompt),
``tools.py`` (the read-only tool catalog), ``gate.py`` (the refusal
gate), ``turn.py`` (one turn's step-by-step mechanics) and
``runner.py`` (``TurnRunner``, the per-bot asyncio scheduling around
it) — see ``docs/specs/2026-10-12-roost-design.md`` and the Night-1
shared contract's "Talk" section.
"""
