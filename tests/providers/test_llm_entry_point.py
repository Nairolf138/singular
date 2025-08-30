from importlib.metadata import EntryPoint

from singular.providers import load_llm_provider
from tests.providers import ep_provider


def test_load_llm_provider_entry_point(monkeypatch):
    ep = EntryPoint(name="ext", value="tests.providers.ep_provider:generate_reply", group="singular.llm")

    def fake_entry_points(*, group):
        assert group == "singular.llm"
        return [ep]

    monkeypatch.setattr("singular.providers.entry_points", fake_entry_points)
    func = load_llm_provider("ext")
    assert func is not None
    assert func("hello") == ep_provider.generate_reply("hello")
