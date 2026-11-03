"""Proof of analysis: hash the snapshot manifest and commit the hash to a NEAR network.

A commit shows that a hash existed no later than the transaction's block. It does not show that the
data behind the hash is correct. The contract is contracts/proof-of-analysis. Signing is left to
near-cli-rs (keychain locally, a key from the environment in CI), so this module never handles a
private key except to pass it along to the CLI.
"""

from __future__ import annotations

import base64
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from capture import manifest as mf

# rpc: answers browsers from other origins (Access-Control-Allow-Origin: *, checked for testnet).
# explorer_tx and the mainnet rpc are the defaults of near-cli-rs 0.30.1 (its config.toml).
NETWORKS = {
    "testnet": {
        "rpc": "https://rpc.testnet.fastnear.com",
        "explorer_tx": "https://explorer.testnet.near.org/transactions/",
    },
    "mainnet": {
        "rpc": "https://archival-rpc.mainnet.fastnear.com",
        "explorer_tx": "https://explorer.near.org/transactions/",
    },
}
STORAGE_YOCTO_PER_BYTE = 10**19  # protocol constant, read from the testnet protocol config
YOCTO_PER_NEAR = 10**24
MARGIN_NEAR = 0.05  # access key, state and the first proofs


class ProofError(RuntimeError):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


def snapshot_end(data_dir: Path) -> str:
    """The last day any file of the snapshot covers."""
    return max(e.date_range[1] for e in mf.read_manifest(data_dir) if e.date_range)


def manifest_sha256(data_dir: Path) -> str:
    return mf.sha256_file(data_dir / mf.MANIFEST_NAME)


def make_run_id(sha256: str, snapshot_day: str) -> str:
    """Deterministic, so the same manifest always maps to the same run (commit is write-once)."""
    return f"capture-ledger-{snapshot_day}-{sha256[:12]}"


def _network(name: str) -> dict:
    if name not in NETWORKS:
        raise ProofError(f"unknown network {name!r}; use one of {', '.join(NETWORKS)}")
    return NETWORKS[name]


# ---------------------------------------------------------------- reading the chain
def _rpc(client: httpx.Client, rpc_url: str, method: str, params: dict) -> dict:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    reply = client.post(rpc_url, json=body, timeout=30).json()
    if "error" in reply:
        error = reply["error"]
        cause = (error.get("cause") or {}).get("name") or error.get("name") or str(error)
        raise ProofError(f"RPC {method} failed: {cause}")
    return reply["result"]


def get(client: httpx.Client, rpc_url: str, contract: str, run_id: str) -> str | None:
    """The hash the contract holds for `run_id` (its view method `get`), or None."""
    args = base64.b64encode(json.dumps({"run_id": run_id}).encode()).decode()
    result = _rpc(
        client,
        rpc_url,
        "query",
        {
            "request_type": "call_function",
            "finality": "final",
            "account_id": contract,
            "method_name": "get",
            "args_base64": args,
        },
    )
    return json.loads(bytes(result["result"]).decode())


def storage_locked_near(wasm_bytes: int) -> float:
    return wasm_bytes * STORAGE_YOCTO_PER_BYTE / YOCTO_PER_NEAR


def preflight(
    client: httpx.Client, rpc_url: str, account: str, wasm_bytes: int, margin: float = MARGIN_NEAR
) -> list[Check]:
    """Can `account` hold the contract code? Reads the account from the chain; changes nothing."""
    try:
        state = _rpc(
            client,
            rpc_url,
            "query",
            {"request_type": "view_account", "finality": "final", "account_id": account},
        )
    except ProofError as exc:
        if "UNKNOWN_ACCOUNT" in str(exc):
            return [Check("account exists", False, f"{account} does not exist on this network")]
        raise
    available = (
        int(state["amount"]) - state["storage_usage"] * STORAGE_YOCTO_PER_BYTE
    ) / YOCTO_PER_NEAR
    needed = storage_locked_near(wasm_bytes) + margin
    return [
        Check("account exists", True, account),
        Check(
            "balance covers the code",
            available >= needed,
            f"needs {needed:.2f} NEAR (code {storage_locked_near(wasm_bytes):.4f} + margin "
            f"{margin}), has {available:.2f} NEAR available",
        ),
    ]


# ---------------------------------------------------------------- proof.json
def near_record(
    network: str, contract: str, signer: str, run_id: str, tx_hash: str, block_height: int
) -> dict:
    net = _network(network)
    return {
        "network": network,
        "contract": contract,
        "signer": signer,
        "run_id": run_id,
        "tx_hash": tx_hash,
        "block_height": block_height,
        "explorer_url": f"{net['explorer_tx']}{tx_hash}",
    }


def write_proof(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)  # readers never see a half-written file


def read_proof(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def site_status(record: dict | None) -> dict:
    """What provenance.json (and so the Methodology page) shows about the proof."""
    near = (record or {}).get("near")
    if not near:
        return {
            "status": "not committed",
            "tx": None,
            "note": "no NEAR commit yet: run `make proof` (see README, 'Verify the proof')",
        }
    return {
        "status": "committed",
        "network": near["network"],
        "contract": near["contract"],
        "run_id": near["run_id"],
        "manifest_sha256": record["manifest_sha256"],
        "tx": near["tx_hash"],
        "block_height": near["block_height"],
        "explorer_url": near["explorer_url"],
        "rpc_url": _network(near["network"])["rpc"],
    }


# ---------------------------------------------------------------- near-cli-rs
def commit_argv(
    near_bin: str,
    contract: str,
    signer: str,
    network: str,
    run_id: str,
    sha256: str,
    public_key: str | None = None,
    private_key: str | None = None,
) -> list[str]:
    """The near-cli-rs command that calls `commit`. Without keys it signs with the keychain."""
    _network(network)
    args = json.dumps({"run_id": run_id, "manifest_sha256": sha256}, separators=(",", ":"))
    argv = [
        near_bin, "contract", "call-function", "as-transaction", contract, "commit",
        "json-args", args, "prepaid-gas", "30 Tgas", "attached-deposit", "0 NEAR",
        "sign-as", signer, "network-config", network,
    ]  # fmt: skip
    if private_key:
        argv += ["sign-with-plaintext-private-key"]
        if public_key:
            argv += ["--signer-public-key", public_key]
        argv += ["--signer-private-key", private_key]
    else:
        argv += ["sign-with-keychain"]
    return argv + ["send"]


# ---------------------------------------------------------------- after the commit
_TX_ID = re.compile(r"Transaction ID:\s*([1-9A-HJ-NP-Za-km-z]{32,44})")


def parse_tx_id(cli_output: str) -> str | None:
    match = _TX_ID.search(cli_output)
    return match.group(1) if match else None


def tx_block_height(client: httpx.Client, rpc_url: str, tx_hash: str, signer: str) -> int:
    """Height of the block that holds the transaction, read from the chain."""
    tx = _rpc(
        client,
        rpc_url,
        "tx",
        {"tx_hash": tx_hash, "sender_account_id": signer, "wait_until": "FINAL"},
    )
    block = _rpc(client, rpc_url, "block", {"block_id": tx["transaction_outcome"]["block_hash"]})
    return int(block["header"]["height"])


# ---------------------------------------------------------------- the whole commit flow
def commit(
    data_dir: Path,
    proof_path: Path,
    *,
    network: str,
    contract: str,
    signer: str,
    client: httpx.Client,
    run: Callable[[list[str]], tuple[int, str]],
    near_bin: str = "near",
    public_key: str | None = None,
    private_key: str | None = None,
    tx_hash: str | None = None,
) -> dict:
    """Commit the manifest hash if the chain does not hold it yet, then record where it is.

    Idempotent: a manifest already committed and recorded is left alone (commit is write-once on
    chain). Success is decided by reading the chain back, never by the CLI's exit code alone.
    """
    sha = manifest_sha256(data_dir)
    run_id = make_run_id(sha, snapshot_end(data_dir))
    rpc = _network(network)["rpc"]
    existing = read_proof(proof_path) or {}
    on_chain = get(client, rpc, contract, run_id)

    recorded = (existing.get("near") or {}).get("run_id") == run_id
    if on_chain == sha and recorded:
        return existing
    if on_chain not in (None, sha):
        raise ProofError(f"{run_id} already holds a different hash on chain: {on_chain}")

    if on_chain is None:
        argv = commit_argv(
            near_bin, contract, signer, network, run_id, sha, public_key, private_key
        )
        code, output = run(argv)
        if code != 0:
            shown = output.replace(private_key, "<key>") if private_key else output
            raise ProofError(f"near CLI failed (exit {code}):\n{shown.strip()[-600:]}")
        tx_hash = tx_hash or parse_tx_id(output)
        if get(client, rpc, contract, run_id) != sha:
            raise ProofError("the chain does not show the committed hash after the CLI call")
    if not tx_hash:
        raise ProofError(
            "the hash is on chain but the transaction id could not be read; pass it with --tx"
        )

    height = tx_block_height(client, rpc, tx_hash, signer)
    record = {
        **existing,
        "run_id": run_id,
        "manifest_sha256": sha,
        "created_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "near": near_record(network, contract, signer, run_id, tx_hash, height),
    }
    write_proof(proof_path, record)
    return record
