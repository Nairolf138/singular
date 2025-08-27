from pathlib import Path
from datetime import datetime
import hashlib

from singular.identity import create_identity, read_identity


def test_create_and_read_identity(tmp_path: Path) -> None:
    path = tmp_path / "id.json"
    data = create_identity("Alice", "42", path)

    assert path.exists()
    loaded = read_identity(path)

    assert loaded == data
    assert loaded.name == "Alice"
    assert loaded.soulseed == "42"
    expected_id = hashlib.sha256(b"Alice:42").hexdigest()
    assert loaded.id == expected_id
    # Ensure born_at is a valid ISO timestamp
    datetime.fromisoformat(loaded.born_at)
