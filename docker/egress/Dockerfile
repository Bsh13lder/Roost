# roost-egress: the one outbound proxy for every bot's computer (see roost/keeper/networks.py).
# Built from the repo root with `make egress-image`. Runs read-only, no capabilities, uid 10003, no port published.
# Copies only what imports cleanly with `python -I`: roost/__init__.py, roost/keeper/__init__.py and proxy.py
# need the standard library only; constants.py needs only decimal, pathlib and typing.
FROM python:3.12-slim-bookworm@sha256:5d9e6adc9abd558bc0ce05f9ab16cef71328916fc9728f6b81e337af86a737e2

ENV PYTHONDONTWRITEBYTECODE=1 \
    ROOST_IN_EGRESS=1
COPY roost/__init__.py /usr/local/lib/python3.12/site-packages/roost/__init__.py
COPY roost/constants.py /usr/local/lib/python3.12/site-packages/roost/constants.py
COPY roost/keeper/__init__.py /usr/local/lib/python3.12/site-packages/roost/keeper/__init__.py
COPY roost/keeper/proxy.py /usr/local/lib/python3.12/site-packages/roost/keeper/proxy.py
COPY roost/keeper/egress_main.py /usr/local/lib/python3.12/site-packages/roost/keeper/egress_main.py

USER 10003
CMD ["python", "-I", "-m", "roost.keeper.egress_main"]
