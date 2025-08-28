from life import quest, synthesis


def test_verification_honours_time_limit():
    spec = quest.Spec(
        name="slow",
        signature="slow()",
        examples=[quest.Example(inputs=[], output=1)],
        constraints=quest.Constraints(pure=True, no_import=True, time_ms_max=50),
    )
    code = (
        "def slow():\n"
        "    for _ in range(10**7):\n"
        "        pass\n"
        "    return 1"
    )
    assert not synthesis._verify(code, spec)
