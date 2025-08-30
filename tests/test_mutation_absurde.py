from singular.organisms.spawn import mutation_absurde


def test_mutation_absurde(tmp_path):
    code = """\
        def add(a, b):
            return a + b
    """.strip() + "\n"

    # Execute original code and record result
    original_ns = {}
    exec(code, original_ns)
    original_result = original_ns["add"](1, 2)

    # Apply the absurd mutation
    mutated_code = mutation_absurde(code)

    # Ensure mutation line is present
    assert "0  # mutation absurde" in mutated_code.splitlines()

    # Execute mutated code and compare results
    mutated_ns = {}
    exec(mutated_code, mutated_ns)
    mutated_result = mutated_ns["add"](1, 2)

    assert mutated_result == original_result
