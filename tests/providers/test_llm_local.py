from singular.providers import llm_local, load_llm_provider


def test_load_llm_provider_local():
    """Ensure the 'local' provider can be loaded."""
    func = load_llm_provider("local")
    assert func is llm_local.generate_reply
