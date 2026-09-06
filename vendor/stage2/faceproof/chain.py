"""Minimal Web3 v7 registry client; contracts never receive biometric material."""
from web3 import Web3
ABI=[{"type":"function","name":"anchor","stateMutability":"nonpayable","inputs":[{"name":"root","type":"bytes32"},{"name":"schema","type":"string"},{"name":"uri","type":"string"}],"outputs":[{"type":"uint256"}]},{"type":"function","name":"idOf","stateMutability":"view","inputs":[{"name":"root","type":"bytes32"}],"outputs":[{"type":"uint256"}]},{"type":"function","name":"get","stateMutability":"view","inputs":[{"name":"id","type":"uint256"}],"outputs":[{"name":"root","type":"bytes32"},{"name":"schema","type":"string"},{"name":"uri","type":"string"},{"name":"submitter","type":"address"},{"name":"timestamp","type":"uint256"}]}]
def client(rpc_url, address): return Web3(Web3.HTTPProvider(rpc_url)), Web3.to_checksum_address(address)
def anchor(rpc_url,address,private_key,root,schema,uri):
    w3,addr=client(rpc_url,address); c=w3.eth.contract(address=addr,abi=ABI); account=w3.eth.account.from_key(private_key)
    tx=c.functions.anchor(bytes.fromhex(root[2:]),schema,uri).build_transaction({"from":account.address,"nonce":w3.eth.get_transaction_count(account.address),"chainId":w3.eth.chain_id})
    signed=account.sign_transaction(tx); receipt=w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction)); return dict(receipt)
def anchored_root(rpc_url,address,root):
    w3,addr=client(rpc_url,address); c=w3.eth.contract(address=addr,abi=ABI); ident=c.functions.idOf(bytes.fromhex(root[2:])).call(); return "0x"+c.functions.get(ident).call()[0].hex()
