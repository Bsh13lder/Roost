"""Events domain: ``EventHub`` — the per-user live event stream (contract's
"Events" section): ``publish`` (persists everything except ``text_delta``,
then fans the frame out live), ``since`` (replay stored events after a
cursor), and ``subscribe`` (an async iterator of one user's live frames).

``roost/gateway/routes/events.py`` is the only consumer of ``since``/
``subscribe``; ``roost/talk/turn.py`` is the only publisher.
"""
