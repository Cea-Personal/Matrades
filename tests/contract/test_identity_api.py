from modules.identity.service import register, verify_password


def test_registration_hashes_password():
    user = register("A@EXAMPLE.COM", "very-long-password")
    assert user.email == "a@example.com"
    assert "very-long-password" not in user.password_hash
    assert verify_password("very-long-password", user.password_hash)
