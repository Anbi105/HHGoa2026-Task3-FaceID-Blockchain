# Local demo environment: Anvil, NOT Polygon Amoy.   (macOS / Linux / WSL)
#
# POSIX counterpart of scripts/demo-anvil.ps1, which is PowerShell-only and so
# left every non-Windows operator without a safe way to run the local demo.
#
# Why this exists: .env sets CHAIN=amoy, RPC_URL=<public Amoy endpoint> and a
# REAL PRIVATE_KEY. Any chain command run without these overrides silently
# talks to Amoy and signs with that key - the failure looks like "contract not
# deployed" and, worse, a working command would spend real testnet POL. This
# script shadows those values for the local run WITHOUT editing .env.
#
# python-dotenv's load_dotenv() does not override variables already present in
# the environment, so exporting them here reliably wins over .env.
#
# Source it (note the leading dot and space):
#
#     . ./scripts/demo-anvil.sh
#
# Anvil keeps chain state in memory only, so after every `anvil` restart you
# must redeploy and re-source this script.

export CHAIN="anvil"
export RPC_URL="http://127.0.0.1:8545"
export PYTHONIOENCODING="utf-8"

_fp_py="./.venv/bin/python"
if [ ! -x "$_fp_py" ]; then
    echo "demo-anvil: no interpreter at $_fp_py - create the venv first:" >&2
    echo "  /opt/homebrew/bin/python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
    return 1 2>/dev/null || exit 1
fi

# Anvil dev account #0, read from faceproof.run so there is exactly one copy of
# it in the repository. It is a world-known key printed in Anvil's own startup
# banner, holds no real funds, and is only ever used against 127.0.0.1.
# Never put a real key here - .env holds the real one and this shadows it.
PRIVATE_KEY="$("$_fp_py" -c 'from faceproof.run import _ANVIL_ACCT0_KEY; print(_ANVIL_ACCT0_KEY)')"
export PRIVATE_KEY

# Channel B transmits a cropped face to a third party when a key is present.
# The local demo must never do that by accident, so the key is cleared here
# regardless of what .env holds.
export SERPAPI_KEY=""

# Registry address from Foundry's own broadcast record for chain 31337, so the
# value tracks redeploys instead of going stale in this file.
_fp_broadcast="contracts/broadcast/Deploy.s.sol/31337/run-latest.json"
if [ -f "$_fp_broadcast" ]; then
    REGISTRY_ADDRESS="$("$_fp_py" -c '
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
a = [t["contractAddress"] for t in d["transactions"] if t.get("contractAddress")]
print(a[-1] if a else "")
' "$_fp_broadcast")"
else
    REGISTRY_ADDRESS=""
fi
export REGISTRY_ADDRESS

printf '\n\033[32mdemo environment\033[0m\n'
printf '  CHAIN            = %s\n' "$CHAIN"
printf '  RPC_URL          = %s\n' "$RPC_URL"
printf '  REGISTRY_ADDRESS = %s\n' "$REGISTRY_ADDRESS"
printf '  PRIVATE_KEY      = <anvil dev account 0, not shown>\n'
printf '  SERPAPI_KEY      = <cleared: Channel B stays offline>\n'

# Self-check: is the node reachable, does that address hold a contract, and how
# many anchors does it already have? A silent wrong address is the single most
# likely way for the demo to fail on camera, so verify rather than assume.
"$_fp_py" -c '
import os, sys
try:
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545", request_kwargs={"timeout": 5}))
    if not w3.is_connected():
        print("  node             : UNREACHABLE - start it with:  anvil"); sys.exit(0)
    print(f"  node             : up, chain {w3.eth.chain_id}, block {w3.eth.block_number}")
    addr = os.environ.get("REGISTRY_ADDRESS", "")
    if not addr:
        print("  registry         : NOT DEPLOYED - run:")
        print("                     .venv/bin/python -m faceproof.run deploy --rpc http://127.0.0.1:8545")
        sys.exit(0)
    a = Web3.to_checksum_address(addr)
    code = w3.eth.get_code(a)
    if len(code) == 0:
        print("  registry         : NO CONTRACT AT THIS ADDRESS (anvil was restarted?) - redeploy")
        sys.exit(0)
    from faceproof.chain import get_contract
    n = get_contract(w3, a).functions.total().call()
    print(f"  registry         : ok, {len(code)} bytes of code, {n} anchor(s) recorded")
except Exception as exc:
    print(f"  self-check       : could not verify ({type(exc).__name__}: {exc})")
'
printf '\n'

unset _fp_py _fp_broadcast
