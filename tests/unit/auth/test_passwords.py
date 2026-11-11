import pytest

from dealdesk.auth.passwords import (
    Argon2Params,
    PasswordHasher,
    PasswordPolicyError,
    check_password_policy,
)

FAST = Argon2Params(time_cost=2, memory_cost_kib=19456, parallelism=1)


@pytest.mark.parametrize(
    ("password", "message"),
    [
        ("short-pass1", "at least 12"),
        ("x" * 129, "at most 128"),
        ("Password1234", "too common"),
        ("abababababab", "too repetitive"),
        ("jane.doe-is-great", "email"),
    ],
)
def test_policy_rejections(password: str, message: str) -> None:
    with pytest.raises(PasswordPolicyError, match=message):
        check_password_policy(password, email="jane.doe@example.com")


@pytest.mark.parametrize(
    "password", ["correct horse battery", "kettle-orbit-lantern", "ÜnïcødePässwörd"]
)
def test_policy_accepts_long_passphrases_without_composition_rules(password: str) -> None:
    check_password_policy(password, email="jane.doe@example.com")


def test_hash_and_verify() -> None:
    hasher = PasswordHasher(FAST)
    encoded = hasher.hash("kettle-orbit-lantern")
    assert encoded.startswith("$argon2id$")
    assert hasher.verify(encoded, "kettle-orbit-lantern")
    assert not hasher.verify(encoded, "kettle-orbit-lanterN")
    assert not hasher.verify("not-a-hash", "kettle-orbit-lantern")
    assert not hasher.verify(None, "dummy-password-for-timing-equalisation")
    assert not hasher.needs_rehash(encoded)
    stronger = PasswordHasher(Argon2Params(time_cost=3, memory_cost_kib=19456, parallelism=1))
    assert stronger.needs_rehash(encoded)
