"""The egress proxy's entry point: it runs only inside the roost-egress container."""

from __future__ import annotations

import asyncio

from roost.keeper import egress_main


class FakeProxy:
    instances: list["FakeProxy"] = []

    def __init__(self, host, port, database_dir) -> None:
        self.args = (host, port, database_dir)
        self.started = self.stopped = False
        FakeProxy.instances.append(self)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


def test_refuses_to_run_outside_the_egress_container(monkeypatch, capsys):
    monkeypatch.delenv("ROOST_IN_EGRESS", raising=False)
    FakeProxy.instances.clear()
    monkeypatch.setattr(egress_main, "EgressProxy", FakeProxy)
    assert egress_main.main() != 0
    assert FakeProxy.instances == []
    assert "roost-egress" in capsys.readouterr().err


def test_a_wrong_value_also_refuses(monkeypatch):
    monkeypatch.setenv("ROOST_IN_EGRESS", "0")
    FakeProxy.instances.clear()
    monkeypatch.setattr(egress_main, "EgressProxy", FakeProxy)
    assert egress_main.main() != 0
    assert FakeProxy.instances == []


def test_binds_the_egress_port_inside_the_container(monkeypatch):
    FakeProxy.instances.clear()
    monkeypatch.setattr(egress_main, "EgressProxy", FakeProxy)

    async def run() -> None:
        stop = asyncio.Event()
        stop.set()
        await egress_main.serve(stop)

    asyncio.run(run())
    (proxy,) = FakeProxy.instances
    assert proxy.args == ("0.0.0.0", 3128, None)
    assert proxy.started and proxy.stopped


def test_the_egress_image_is_pinned_unprivileged_and_exposes_nothing():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "docker" / "egress" / "Dockerfile").read_text()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    assert any(ln.startswith("FROM python:3.12-slim-bookworm@sha256:") for ln in lines)
    assert "USER 10003" in lines
    assert not [ln for ln in lines if ln.startswith("EXPOSE")]
    assert "ENV PYTHONDONTWRITEBYTECODE=1 ROOST_IN_EGRESS=1" in " ".join(lines).replace("\\ ", "")
    assert 'CMD ["python", "-I", "-m", "roost.keeper.egress_main"]' in lines
    copied = {ln.split()[1] for ln in lines if ln.startswith("COPY")}
    assert copied == {"roost/__init__.py", "roost/constants.py", "roost/keeper/__init__.py",
                      "roost/keeper/proxy.py", "roost/keeper/egress_main.py"}
