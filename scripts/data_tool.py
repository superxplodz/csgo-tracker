"""Edit the encrypted site data by hand.

  SITE_PASSWORD=... python scripts/data_tool.py open     # data.enc -> data.json (never commit data.json)
  SITE_PASSWORD=... python scripts/data_tool.py seal     # data.json -> data.enc
  OLD_PASSWORD=... SITE_PASSWORD=... python scripts/data_tool.py repass   # change the password
"""
import json
import os
import sys

from crypto_box import decrypt, encrypt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENC, PLAIN = os.path.join(ROOT, "data.enc"), os.path.join(ROOT, "data.json")


def main():
    cmd, pw = (sys.argv[1] if len(sys.argv) > 1 else ""), os.environ.get("SITE_PASSWORD", "")
    if cmd == "open":
        json.dump(decrypt(open(ENC).read(), pw), open(PLAIN, "w"), ensure_ascii=False, indent=1)
    elif cmd == "seal":
        open(ENC, "w").write(encrypt(json.load(open(PLAIN)), pw))
    elif cmd == "repass":
        open(ENC, "w").write(encrypt(decrypt(open(ENC).read(), os.environ["OLD_PASSWORD"]), pw))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
