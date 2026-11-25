from singular.life import quest, synthesis


def test_verification_honours_time_limit(monkeypatch):
    spec = quest.Spec(
        name="slow",
        signature="slow()",
        examples=[quest.Example(inputs=[], output=1)],
        constraints=quest.Constraints(pure=True, no_import=True, time_ms_max=50),
    )
    code = (
        "def slow():\n" "    for _ in range(10**7):\n" "        pass\n" "    return 1"
    )
    observed: list[float | None] = []

    def timed_out(_code: str, *, timeout: float | None = None) -> None:
        observed.append(timeout)
        raise TimeoutError("sandbox execution timed out")

    monkeypatch.setattr("singular.life.skill_validation.sandbox.run", timed_out)
    result = synthesis.validate_generated_skill(
        code,
        expected_symbol=spec.name,
        examples=[(example.inputs, example.output) for example in spec.examples],
        timeout=spec.constraints.time_ms_max / 1000,
    )

    assert observed == [0.05]
    assert not result.ok
    assert "timed out" in result.reason
