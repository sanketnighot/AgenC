"""
Deploy BountyEscrow to Base Sepolia.

Usage:
  BASE_SEPOLIA_RPC=https://sepolia.base.org \
  ARBITER_PRIVATE_KEY=0x... \
  python contracts/deploy.py

Outputs contract address + Basescan TX link.
Saves ABI to agenc-api/bounty_escrow_abi.json for use by payment.py.
"""
import json
import os
import pathlib

from web3 import Web3
from solcx import compile_source, install_solc

install_solc("0.8.20")

RPC = os.environ["BASE_SEPOLIA_RPC"]
PRIVATE_KEY = os.environ["ARBITER_PRIVATE_KEY"]

w3 = Web3(Web3.HTTPProvider(RPC))
assert w3.is_connected(), "Cannot connect to RPC"

account = w3.eth.account.from_key(PRIVATE_KEY)
print(f"Deploying from: {account.address}")
print(f"Balance: {w3.from_wei(w3.eth.get_balance(account.address), 'ether')} ETH")

src = pathlib.Path("contracts/BountyEscrow.sol").read_text()
compiled = compile_source(src, output_values=["abi", "bin"], solc_version="0.8.20")
contract_interface = compiled["<stdin>:BountyEscrow"]
abi = contract_interface["abi"]
bytecode = contract_interface["bin"]

contract = w3.eth.contract(abi=abi, bytecode=bytecode)
tx = contract.constructor(account.address).build_transaction({
    "from": account.address,
    "nonce": w3.eth.get_transaction_count(account.address),
    "gas": 500_000,
    "gasPrice": w3.eth.gas_price,
})
signed = account.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
print(f"TX sent: {tx_hash.hex()}")
print("Waiting for confirmation...")

receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
contract_address = receipt["contractAddress"]

print(f"\n✅ Contract deployed: {contract_address}")
print(f"   Basescan: https://sepolia.basescan.org/tx/{tx_hash.hex()}")
print(f"\nAdd to .env:")
print(f"  CONTRACT_ADDRESS={contract_address}")
print(f"\nAdd to agenc-frontend/.env.local:")
print(f"  NEXT_PUBLIC_CONTRACT_ADDRESS={contract_address}")

abi_path = pathlib.Path("agenc-api/bounty_escrow_abi.json")
abi_path.write_text(json.dumps(abi, indent=2))
print(f"\nABI saved to {abi_path}")
