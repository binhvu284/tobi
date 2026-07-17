"""
Vault purpose-bound payload helpers (queue #20, T02) — encrypt_payload /
decrypt_payload / can_encrypt_payloads.

Plain python, no pytest, isolated temp DB:
    python tests/test_vault_payload.py

Covers: roundtrip through an unlocked vault; ciphertext is not the plaintext;
purpose binding (a payload encrypted for one purpose can't be decrypted as
another); empty-purpose rejection; VaultLocked when locked; and that a payload
survives lock and decrypts again after re-unlock with the same master password.
"""
import os
import sys
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="tobi_vp_"), "agent.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.database import init_database, get_connection  # noqa: E402
from core import vault  # noqa: E402

init_database()
conn = get_connection()

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


def raises(fn, exc=Exception) -> bool:
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


MASTER = "correct horse battery staple"
PURPOSE = "brain.memory:7:distilled_text"
SECRET = "Owner's private recovery phrase — SUPER_SECRET_TOKEN_9137"

ok("crypto available", vault.CRYPTO_AVAILABLE)

# locked before setup — helpers must fail closed
ok("can_encrypt_payloads False before setup", vault.can_encrypt_payloads() is False)
ok("encrypt raises VaultLocked before setup", raises(lambda: vault.encrypt_payload(PURPOSE, SECRET), vault.VaultLocked))

# setup leaves the vault unlocked
vault.setup(conn, MASTER, import_env=False)
ok("can_encrypt_payloads True after setup", vault.can_encrypt_payloads() is True)

# roundtrip
ct, nonce = vault.encrypt_payload(PURPOSE, SECRET)
ok("ciphertext is bytes", isinstance(ct, (bytes, bytearray)))
ok("nonce is bytes", isinstance(nonce, (bytes, bytearray)))
ok("ciphertext is not the plaintext", SECRET.encode("utf-8") not in bytes(ct))
ok("decrypt roundtrip", vault.decrypt_payload(PURPOSE, ct, nonce) == SECRET)

# purpose binding — AAD mismatch fails closed
ok("wrong purpose fails to decrypt", raises(lambda: vault.decrypt_payload("brain.memory:8:distilled_text", ct, nonce)))
ok("tampered ciphertext fails to decrypt",
   raises(lambda: vault.decrypt_payload(PURPOSE, bytes(ct)[:-1] + bytes([bytes(ct)[-1] ^ 0x01]), nonce)))

# input validation
ok("empty purpose rejected", raises(lambda: vault.encrypt_payload("   ", SECRET), vault.VaultError))

# locked → both directions raise VaultLocked; ciphertext persists in memory
vault.lock()
ok("can_encrypt_payloads False when locked", vault.can_encrypt_payloads() is False)
ok("encrypt raises VaultLocked when locked", raises(lambda: vault.encrypt_payload(PURPOSE, SECRET), vault.VaultLocked))
ok("decrypt raises VaultLocked when locked", raises(lambda: vault.decrypt_payload(PURPOSE, ct, nonce), vault.VaultLocked))

# re-unlock with the same master → same key → old ciphertext decrypts again
vault.unlock(conn, MASTER)
ok("decrypt works again after re-unlock", vault.decrypt_payload(PURPOSE, ct, nonce) == SECRET)

# wrong master cannot unlock (so cannot decrypt)
vault.lock()
ok("wrong master rejected", raises(lambda: vault.unlock(conn, "not the master"), vault.VaultError))
ok("still locked after failed unlock", vault.can_encrypt_payloads() is False)

print(f"\n{PASS} checks passed")
