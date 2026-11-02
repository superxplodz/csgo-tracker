"""Open or seal the data file by hand.

  SITE_PASSWORD=... python scripts/data_tool.py open    # data.enc -> data.json (do NOT commit data.json)
  SITE_PASSWORD=... python scripts/data_tool.py seal    # data.json -> data.enc
  OLD_PASSWORD=... SITE_PASSWORD=... python scripts/data_tool.py repass   # change password
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from crypto_box import encrypt, decrypt

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
enc, plain = os.path.join(root, "data.enc"), os.path.join(root, "data.json")
pw = os.environ["SITE_PASSWORD"]
cmd = sys.argv[1] if len(sys.argv) > 1 else ""
if cmd == "open":
    json.dump(decrypt(open(enc).read(), pw), open(plain, "w"), ensure_ascii=False, indent=1)
elif cmd == "seal":
    open(enc, "w").write(encrypt(json.load(open(plain)), pw))
elif cmd == "repass":
    open(enc, "w").write(encrypt(decrypt(open(enc).read(), os.environ["OLD_PASSWORD"]), pw))
else:
    sys.exit(__doc__)
