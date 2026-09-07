# Local demo environment: Anvil, NOT Polygon Amoy.
#
# Why this exists: .env sets CHAIN=amoy and RPC_URL=<public Amoy endpoint>.
# Any chain command run without these overrides silently talks to Amoy, where
# the local registry does not exist - the failure looks like "contract not
# deployed" and wastes demo time. This script shadows those values for the
# local run WITHOUT editing .env, so no testnet POL can be spent by accident.
#
# Dot-source it (note the leading dot and space):
#
#     . .\scripts\demo-anvil.ps1
#
# If PowerShell refuses to run it ("running scripts is disabled"), either
# start the shell with:
#     powershell -ExecutionPolicy Bypass
# or allow local scripts once for your user:
#     Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#
# Anvil keeps chain state in memory only, so after every `anvil` restart you
# must redeploy and re-run this script.

$env:CHAIN            = "anvil"
$env:RPC_URL          = "http://127.0.0.1:8545"
$env:PYTHONIOENCODING = "utf-8"

$py = ".\.venv\Scripts\python.exe"

# Anvil dev account #0, read from faceproof.run so there is exactly one copy of
# it in the repository. It is a world-known key printed in Anvil's own startup
# banner, holds no real funds, and is only ever used against 127.0.0.1.
# Never put a real key here - .env holds the real one and this shadows it.
$env:PRIVATE_KEY = (& $py -c "from faceproof.run import _ANVIL_ACCT0_KEY; print(_ANVIL_ACCT0_KEY)")

# Registry address from Foundry's own broadcast record for chain 31337, so the
# value tracks redeploys instead of going stale in this file.
$broadcast = Join-Path "contracts" "broadcast\Deploy.s.sol\31337\run-latest.json"

if (Test-Path $broadcast) {
    $env:REGISTRY_ADDRESS = (& $py -c @"
import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
a = [t['contractAddress'] for t in d['transactions'] if t.get('contractAddress')]
print(a[-1] if a else '')
"@ $broadcast)
} else {
    $env:REGISTRY_ADDRESS = ""
}

Write-Host ""
Write-Host "demo environment" -ForegroundColor Green
Write-Host "  CHAIN            = $env:CHAIN"
Write-Host "  RPC_URL          = $env:RPC_URL"
Write-Host "  REGISTRY_ADDRESS = $env:REGISTRY_ADDRESS"
Write-Host "  PRIVATE_KEY      = <anvil dev account 0, not shown>"

# Self-check: is the node reachable, does that address hold a contract, and how
# many anchors does it already have? A silent wrong address is the single most
# likely way for the demo to fail on camera, so verify rather than assume.
& $py -c @"
import os, sys
try:
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545', request_kwargs={'timeout': 5}))
    if not w3.is_connected():
        print('  node             : UNREACHABLE - start it with:  anvil'); sys.exit(0)
    print(f'  node             : up, chain {w3.eth.chain_id}, block {w3.eth.block_number}')
    addr = os.environ.get('REGISTRY_ADDRESS', '')
    if not addr:
        print('  registry         : NOT DEPLOYED - run:')
        print('                     .\\\\.venv\\\\Scripts\\\\python.exe -m faceproof.run deploy --rpc http://127.0.0.1:8545')
        sys.exit(0)
    a = Web3.to_checksum_address(addr)
    code = w3.eth.get_code(a)
    if len(code) == 0:
        print('  registry         : NO CONTRACT AT THIS ADDRESS (anvil was restarted?) - redeploy')
        sys.exit(0)
    from faceproof.chain import get_contract
    n = get_contract(w3, a).functions.total().call()
    print(f'  registry         : ok, {len(code)} bytes of code, {n} anchor(s) recorded')
except Exception as exc:
    print(f'  self-check       : could not verify ({type(exc).__name__}: {exc})')
"@
Write-Host ""
