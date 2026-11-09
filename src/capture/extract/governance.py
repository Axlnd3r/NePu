"""House of Stake proposals read from the `vote.dao` contract on NEAR mainnet (no key needed).

One view call, `get_proposal`, at the final block. The reply is stored as it came (the proposal
decoded from the call's bytes, plus the block it was read at) in data/reference/, and `summarize`
derives the figures the thesis uses. The contract stores votes per option index and no option
labels, so the summary reports the share of each index and the contract's own status.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import httpx

from capture.extract.common import with_retries

RPC_URL = "https://rpc.mainnet.fastnear.com"
CONTRACT = "vote.dao"
HSP029_ID = 29
NS_PER_S = 1_000_000_000


def _iso(ns: int) -> str:
    return datetime.fromtimestamp(ns // NS_PER_S, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_proposal(
    proposal_id: int = HSP029_ID,
    *,
    contract: str = CONTRACT,
    rpc_url: str = RPC_URL,
    client: httpx.Client | None = None,
) -> dict:
    """{"request": ..., "block_height", "block_hash", "proposal": <get_proposal reply>}."""
    args = base64.b64encode(json.dumps({"proposal_id": proposal_id}).encode()).decode()
    params = {
        "request_type": "call_function",
        "finality": "final",
        "account_id": contract,
        "method_name": "get_proposal",
        "args_base64": args,
    }
    own = client is None
    client = client or httpx.Client(timeout=60)

    def call() -> dict:
        body = {"jsonrpc": "2.0", "id": 1, "method": "query", "params": params}
        reply = client.post(rpc_url, json=body).json()
        if "error" in reply or "error" in reply.get("result", {}):
            raise RuntimeError(f"get_proposal({proposal_id}) on {contract} failed: {reply}")
        return reply["result"]

    try:
        result = with_retries(call, retry_on=(httpx.TransportError,))
    finally:
        if own:
            client.close()
    return {
        "request": {"rpc": rpc_url, **{k: v for k, v in params.items() if k != "args_base64"}},
        "args": {"proposal_id": proposal_id},
        "block_height": result["block_height"],
        "block_hash": result["block_hash"],
        "proposal": json.loads(bytes(result["result"]).decode()),
    }


def summarize(record: dict) -> dict:
    """The figures the thesis quotes, all derived from the stored reply."""
    p = record["proposal"]
    cast = int(p["total_votes"]["total_venear"])
    eligible = int(p["snapshot_and_state"]["total_venear"])
    shares = [int(v["total_venear"]) / cast if cast else 0.0 for v in p["votes"]]
    start = int(p["voting_start_time_ns"])
    voting_end = start + int(p["voting_duration_ns"])
    timelock_end = voting_end + int(p["timelock_duration_ns"])
    return {
        "contract": record["request"]["account_id"],
        "proposal_id": p["id"],
        "title": p["title"],
        "link": p["link"],
        "status": p["status"],
        "read_at_block": record["block_height"],
        "option_shares": shares,
        "top_option_share": max(shares) if shares else None,
        "voters": p["total_votes"]["total_votes"],
        "turnout": cast / eligible if eligible else None,
        "quorum_threshold": p["quorum_threshold_bps"] / 10_000,
        "approval_threshold": p["approval_threshold_bps"] / 10_000,
        "voting_start_utc": _iso(start),
        "voting_end_utc": _iso(voting_end),
        "timelock_end_utc": _iso(timelock_end),
        "note": (
            "The contract stores votes per option index and no option labels; the status is the "
            "contract's own. 'Timelock' means the vote has closed and the proposal is waiting out "
            "its timelock; the issuance ramp itself still needs validators to adopt it."
        ),
    }
