"""Encrypt / decrypt the site's data file.

Format (JSON): {"v":1,"kdf":"PBKDF2-SHA256","iter":N,"salt":b64,"iv":b64,"ct":b64}
ct is AES-256-GCM ciphertext with the 16-byte tag appended, which is what
the browser's WebCrypto API expects, so index.html can decrypt it.
"""
import base64, json, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ITER = 250_000


def _key(password: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return kdf.derive(password.encode("utf-8"))


def encrypt(obj, password: str) -> str:
    salt, iv = os.urandom(16), os.urandom(12)
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ct = AESGCM(_key(password, salt, ITER)).encrypt(iv, data, None)
    b = lambda x: base64.b64encode(x).decode()
    return json.dumps({"v": 1, "kdf": "PBKDF2-SHA256", "iter": ITER, "salt": b(salt), "iv": b(iv), "ct": b(ct)})


def decrypt(text: str, password: str):
    env = json.loads(text)
    d = lambda k: base64.b64decode(env[k])
    raw = AESGCM(_key(password, d("salt"), env["iter"])).decrypt(d("iv"), d("ct"), None)
    return json.loads(raw)
