import pytest

from singular.providers import ProviderMisconfiguredError, _load_provider_contract


def test_load_provider_contract_raises_explicit_error_when_dependency_is_missing(monkeypatch):
    module_name = "singular.providers.llm_broken"

    def fake_import_module(imported_name):
        assert imported_name == module_name
        raise ModuleNotFoundError("No module named 'missing_dependency'", name="missing_dependency")

    monkeypatch.setattr("singular.providers.import_module", fake_import_module)

    with pytest.raises(ProviderMisconfiguredError, match="missing dependency 'missing_dependency'"):
        _load_provider_contract("broken")
