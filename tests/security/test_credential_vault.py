from uuid import uuid4

from modules.credentials.vault import CredentialVault


def test_secret_is_encrypted_masked_and_owner_scoped():
    owner = uuid4()
    vault = CredentialVault(b"0" * 32)
    item = vault.store(owner, "provider", "topsecret123")
    assert b"topsecret" not in item.ciphertext
    assert "topsecret" not in str(vault.public(item))
    assert vault.resolve_for_adapter(owner, item.id) == "topsecret123"
