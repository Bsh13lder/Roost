"""Gateway routers, one module per resource (``bots``, and later ``threads``,
``desk``, ``events``, ``static``) — each exports an ``APIRouter`` that
``roost/gateway/app.py`` mounts with ``app.include_router``.
"""
