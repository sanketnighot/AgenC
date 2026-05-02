"""On-chain payment settlement for AgenC bounties via BountyEscrow.sol on Base Sepolia."""
import asyncio
import json
import logging
import os
import pathlib

from web3 import Web3

logger = logging.getLogger(__name__)

_w3: Web3 | None = None
_contract = None


def _setup() -> None:
    global _w3, _contract
    if _w3 is not None:
        return
    rpc = os.environ.get("BASE_SEPOLIA_RPC", "")
    private_key = os.environ.get("ARBITER_PRIVATE_KEY", "")
    contract_address = os.environ.get("CONTRACT_ADDRESS", "")
    if not all([rpc, private_key, contract_address]):
        raise RuntimeError(
            "Missing blockchain env vars: BASE_SEPOLIA_RPC, ARBITER_PRIVATE_KEY, CONTRACT_ADDRESS"
        )
    _w3 = Web3(Web3.HTTPProvider(rpc))
    abi_path = pathlib.Path(__file__).parent / "bounty_escrow_abi.json"
    abi = json.loads(abi_path.read_text())
    addr = Web3.to_checksum_address(contract_address)
    _contract = _w3.eth.contract(address=addr, abi=abi)


def _bounty_id_bytes32(bounty_id: str) -> bytes:
    assert _w3 is not None
    return _w3.keccak(text=bounty_id)


def _send_tx(fn) -> str:
    """Sign and broadcast a contract transaction; return tx_hash hex. Blocking."""
    assert _w3 is not None
    account = _w3.eth.account.from_key(os.environ["ARBITER_PRIVATE_KEY"])
    tx = fn.build_transaction({
        "from": account.address,
        "nonce": _w3.eth.get_transaction_count(account.address),
        "gas": 200_000,
        "gasPrice": _w3.eth.gas_price,
    })
    signed = account.sign_transaction(tx)
    tx_hash = _w3.eth.send_raw_transaction(signed.raw_transaction)
    _w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    return tx_hash.hex()


def _is_configured() -> bool:
    return all([
        os.environ.get("BASE_SEPOLIA_RPC"),
        os.environ.get("ARBITER_PRIVATE_KEY"),
        os.environ.get("CONTRACT_ADDRESS"),
        pathlib.Path(__file__).parent.joinpath("bounty_escrow_abi.json").exists(),
    ])


async def settle_bounty(bounty_id: str, worker_addresses: list[str], amounts_wei: list[int]) -> str:
    """Distribute ETH to workers on-chain. Returns Basescan URL."""
    if not _is_configured():
        logger.warning("Blockchain not configured — skipping settlement for %s", bounty_id)
        return ""
    _setup()
    assert _contract is not None
    bid = _bounty_id_bytes32(bounty_id)
    addrs = [Web3.to_checksum_address(a) for a in worker_addresses]
    fn = _contract.functions.distribute(bid, addrs, amounts_wei)
    tx_hash = await asyncio.to_thread(_send_tx, fn)
    url = f"https://sepolia.basescan.org/tx/{tx_hash}"
    logger.info("Settled bounty %s → TX %s", bounty_id, url)
    return url


async def refund_bounty(bounty_id: str) -> str:
    """Refund ETH to the original poster on-chain. Returns Basescan URL."""
    if not _is_configured():
        logger.warning("Blockchain not configured — skipping refund for %s", bounty_id)
        return ""
    _setup()
    assert _contract is not None
    bid = _bounty_id_bytes32(bounty_id)
    fn = _contract.functions.refund(bid)
    tx_hash = await asyncio.to_thread(_send_tx, fn)
    url = f"https://sepolia.basescan.org/tx/{tx_hash}"
    logger.info("Refunded bounty %s → TX %s", bounty_id, url)
    return url
