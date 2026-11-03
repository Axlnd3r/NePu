"""Proof of analysis: run id, on-chain read, balance preflight, proof.json, near-cli-rs commands.

No test here touches a network: HTTP goes through httpx.MockTransport and the near CLI is only
asked for the argument list it would run.
"""

import base64
import json

import httpx
import pytest

from capture import build, config, proof
from capture import manifest as mf

HASH = "48c59060cee309e2aafb62614dfb24454828bf5ae8f534bd52154165b5b8c096"
CONTRACT = "ledger-proof.testnet"


def rpc_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def rpc_result(value: dict) -> httpx.Response:
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": value})


# ---------------------------------------------------------------- run id
def test_run_id_names_the_snapshot_day_and_the_start_of_the_hash() -> None:
    run_id = proof.make_run_id(HASH, "2026-11-01")
    assert run_id == "capture-ledger-2026-11-01-48c59060cee3"
    assert len(run_id.encode()) <= 128  # the contract's limit


def test_run_id_changes_when_the_manifest_changes() -> None:
    other = "0" * 64
    assert proof.make_run_id(HASH, "2026-11-01") != proof.make_run_id(other, "2026-11-01")


def test_snapshot_end_is_the_last_day_any_file_covers(data_dir) -> None:
    ends = [e.date_range[1] for e in mf.read_manifest(data_dir) if e.date_range]
    assert proof.snapshot_end(data_dir) == max(ends) == "2026-11-01"


def test_manifest_hash_is_the_sha256_of_the_file_bytes(data_dir) -> None:
    import hashlib

    expected = hashlib.sha256((data_dir / "manifest.json").read_bytes()).hexdigest()
    assert proof.manifest_sha256(data_dir) == expected


# ---------------------------------------------------------------- reading the chain
def test_get_asks_the_contract_view_method_with_the_run_id() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return rpc_result({"result": list(json.dumps(HASH).encode()), "logs": []})

    value = proof.get(rpc_client(handler), "https://rpc.example", CONTRACT, "run-1")
    assert value == HASH
    assert seen["method"] == "query"
    params = seen["params"]
    assert params["request_type"] == "call_function"
    assert params["finality"] == "final"
    assert params["account_id"] == CONTRACT and params["method_name"] == "get"
    assert json.loads(base64.b64decode(params["args_base64"])) == {"run_id": "run-1"}


def test_get_returns_none_when_nothing_was_committed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return rpc_result({"result": list(b"null"), "logs": []})

    assert proof.get(rpc_client(handler), "https://rpc.example", CONTRACT, "run-1") is None


def test_get_reports_a_chain_error_instead_of_returning_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"error": {"name": "HANDLER_ERROR", "cause": {"name": "NO_CONTRACT_CODE"}}}
        )

    with pytest.raises(proof.ProofError, match="NO_CONTRACT_CODE"):
        proof.get(rpc_client(handler), "https://rpc.example", CONTRACT, "run-1")


# ---------------------------------------------------------------- balance preflight
def test_the_code_locks_one_hundred_thousandth_of_a_near_per_byte() -> None:
    assert proof.storage_locked_near(105_951) == pytest.approx(1.05951)


def account_response(amount_near: float, storage: int = 182) -> dict:
    return {"amount": str(int(amount_near * 10**24)), "locked": "0", "storage_usage": storage,
            "code_hash": "11111111111111111111111111111111"}  # fmt: skip


def test_preflight_passes_when_the_account_covers_code_and_a_margin() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return rpc_result(account_response(1.5))

    checks = proof.preflight(
        rpc_client(handler), "https://rpc.example", "a.testnet", wasm_bytes=105_951
    )
    assert {c.name: c.ok for c in checks} == {
        "account exists": True,
        "balance covers the code": True,
    }


def test_preflight_says_how_much_is_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return rpc_result(account_response(0.4))

    checks = proof.preflight(
        rpc_client(handler), "https://rpc.example", "a.testnet", wasm_bytes=105_951
    )
    by = {c.name: c for c in checks}
    assert not by["balance covers the code"].ok
    assert (
        "needs 1.1" in by["balance covers the code"].detail
        and "has 0.4" in by["balance covers the code"].detail
    )


def test_preflight_reports_a_missing_account_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"cause": {"name": "UNKNOWN_ACCOUNT"}}})

    checks = proof.preflight(
        rpc_client(handler), "https://rpc.example", "a.testnet", wasm_bytes=105_951
    )
    assert [(c.name, c.ok) for c in checks] == [("account exists", False)]


# ---------------------------------------------------------------- proof.json
def test_record_links_the_transaction_and_names_the_network() -> None:
    rec = proof.near_record(
        network="testnet", contract=CONTRACT, signer="ledger-proof.testnet",
        run_id="run-1", tx_hash="Abc123", block_height=1234,
    )  # fmt: skip
    assert rec["network"] == "testnet"
    assert rec["explorer_url"] == "https://explorer.testnet.near.org/transactions/Abc123"
    assert rec["tx_hash"] == "Abc123" and rec["block_height"] == 1234


def test_a_record_for_mainnet_uses_the_mainnet_explorer() -> None:
    rec = proof.near_record("mainnet", "p.near", "p.near", "run-1", "Abc123", 1)
    assert rec["explorer_url"].startswith("https://explorer.near.org/transactions/")


def test_proof_file_round_trips_with_lf_endings(tmp_path) -> None:
    path = tmp_path / "proof.json"
    assert proof.read_proof(path) is None
    proof.write_proof(path, {"run_id": "run-1", "manifest_sha256": HASH, "near": None})
    assert b"\r" not in path.read_bytes()
    assert proof.read_proof(path)["run_id"] == "run-1"


def test_site_proof_says_not_committed_without_a_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(build, "PROOF_FILE", tmp_path / "missing.json")
    assert proof.site_status(proof.read_proof(build.PROOF_FILE))["status"] == "not committed"


def test_site_proof_flags_a_proof_made_for_an_older_snapshot(tmp_path) -> None:
    path = tmp_path / "proof.json"
    near = proof.near_record("testnet", CONTRACT, CONTRACT, "run-1", "Abc123", 99)
    proof.write_proof(path, {"run_id": "run-1", "manifest_sha256": HASH, "near": near})
    record = proof.read_proof(path)
    assert proof.site_status(record, current_sha256=HASH)["current"] is True
    assert proof.site_status(record, current_sha256="0" * 64)["current"] is False
    assert proof.site_status(None, current_sha256=HASH).get("current") is None


def test_site_proof_reports_what_was_committed_and_where(tmp_path) -> None:
    path = tmp_path / "proof.json"
    near = proof.near_record("testnet", CONTRACT, CONTRACT, "run-1", "Abc123", 99)
    proof.write_proof(path, {"run_id": "run-1", "manifest_sha256": HASH, "near": near})
    status = proof.site_status(proof.read_proof(path))
    assert status["status"] == "committed" and status["network"] == "testnet"
    assert status["run_id"] == "run-1" and status["manifest_sha256"] == HASH
    assert status["rpc_url"] == proof.NETWORKS["testnet"]["rpc"]


# ---------------------------------------------------------------- near-cli-rs commands
def test_commit_with_the_keychain_never_puts_a_key_on_the_command_line() -> None:
    argv = proof.commit_argv("near", CONTRACT, "signer.testnet", "testnet", "run-1", HASH)
    assert argv[:4] == ["near", "contract", "call-function", "as-transaction"]
    assert argv[4:6] == [CONTRACT, "commit"]
    assert argv[6] == "json-args" and json.loads(argv[7]) == {
        "run_id": "run-1",
        "manifest_sha256": HASH,
    }
    assert argv[8:12] == ["prepaid-gas", "30 Tgas", "attached-deposit", "0 NEAR"]
    assert argv[12:14] == ["sign-as", "signer.testnet"]
    assert argv[14:16] == ["network-config", "testnet"]
    assert argv[16:] == ["sign-with-keychain", "send"]
    assert "private" not in " ".join(argv)


def test_commit_in_ci_signs_with_a_key_given_by_the_environment() -> None:
    argv = proof.commit_argv(
        "near", CONTRACT, "signer.testnet", "testnet", "run-1", HASH,
        public_key="ed25519:PUB", private_key="ed25519:PRIV",
    )  # fmt: skip
    assert argv[16] == "sign-with-plaintext-private-key"
    assert argv[argv.index("--signer-public-key") + 1] == "ed25519:PUB"
    assert argv[argv.index("--signer-private-key") + 1] == "ed25519:PRIV"
    assert argv[-1] == "send"


def test_unknown_network_is_refused() -> None:
    with pytest.raises(proof.ProofError, match="network"):
        proof.commit_argv("near", CONTRACT, "s.testnet", "devnet", "run-1", HASH)


def test_settings_know_the_proof_variables() -> None:
    for key in ("PROOF_NETWORK", "PROOF_ACCOUNT_ID", "PROOF_CONTRACT_ID", "PROOF_PRIVATE_KEY"):
        assert key in config.SETTING_KEYS


# ---------------------------------------------------------------- after the commit
TX = "9mSmCnrqVn1RoTpQ2zKkYCJwKr4xCxYbhGYzTnVxS8vE"


def test_block_height_comes_from_the_chain_not_from_the_cli_output() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["method"])
        if body["method"] == "tx":
            assert body["params"]["tx_hash"] == TX
            assert body["params"]["sender_account_id"] == "signer.testnet"
            return rpc_result({"transaction_outcome": {"block_hash": "BLOCKHASH"}})
        assert body["method"] == "block" and body["params"] == {"block_id": "BLOCKHASH"}
        return rpc_result({"header": {"height": 4321}})

    height = proof.tx_block_height(rpc_client(handler), "https://rpc.example", TX, "signer.testnet")
    assert height == 4321 and calls == ["tx", "block"]


REAL_CLI_OUTPUT = """
├  Transaction Execution Info:
│    Transaction ID: H2TqexvmEcTAQvkzvgYnGQ7dLkEtP3nTnakmPUaJBpKM
│    To see the transaction in the transaction explorer, please open this url in your browser:
│    https://explorer.testnet.near.org/transactions/H2TqexvmEcTAQvkzvgYnGQ7dLkEtP3nTnakmPUaJBpKM
"""


def test_tx_id_is_read_from_real_near_cli_output() -> None:
    """Real near-cli-rs 0.30.1 output (account creation), box-drawing prefix included."""
    assert proof.parse_tx_id(REAL_CLI_OUTPUT) == "H2TqexvmEcTAQvkzvgYnGQ7dLkEtP3nTnakmPUaJBpKM"


def test_tx_id_is_read_from_a_plain_line() -> None:
    assert proof.parse_tx_id(f"Transaction ID: {TX}\n") == TX


def test_tx_id_is_none_when_the_output_has_none() -> None:
    assert proof.parse_tx_id("error: something failed\n") is None


# ---------------------------------------------------------------- the whole commit flow
class FakeChain:
    """Answers the RPC calls the flow makes; `committed` flips when the fake CLI 'sends'."""

    def __init__(self, committed: str | None = None) -> None:
        self.committed, self.cli_calls = committed, []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "query":
            return rpc_result({"result": list(json.dumps(self.committed).encode()), "logs": []})
        if body["method"] == "tx":
            return rpc_result({"transaction_outcome": {"block_hash": "BH"}})
        return rpc_result({"header": {"height": 777}})

    def run(self, argv: list[str]) -> tuple[int, str]:
        self.cli_calls.append(argv)
        self.committed = json.loads(argv[7])["manifest_sha256"]
        return 0, f"Transaction ID: {TX}\n"


def commit_flow(chain: FakeChain, data_dir, proof_path, **extra) -> dict:
    return proof.commit(
        data_dir, proof_path, network="testnet", contract=CONTRACT, signer="signer.testnet",
        client=rpc_client(chain.handler), run=chain.run, **extra,
    )  # fmt: skip


def test_commit_sends_once_verifies_on_chain_and_writes_proof_json(data_dir, tmp_path) -> None:
    chain, path = FakeChain(), tmp_path / "proof.json"
    rec = commit_flow(chain, data_dir, path)
    sha = proof.manifest_sha256(data_dir)
    assert len(chain.cli_calls) == 1
    assert rec["manifest_sha256"] == sha and rec["run_id"].endswith(sha[:12])
    assert rec["near"]["tx_hash"] == TX and rec["near"]["block_height"] == 777
    assert proof.read_proof(path) == rec


def test_commit_is_idempotent_when_the_proof_is_already_on_chain(data_dir, tmp_path) -> None:
    chain, path = FakeChain(), tmp_path / "proof.json"
    first = commit_flow(chain, data_dir, path)
    second = commit_flow(chain, data_dir, path)
    assert len(chain.cli_calls) == 1 and second == first


def test_commit_keeps_the_opentimestamps_entry_of_the_same_run(data_dir, tmp_path) -> None:
    run_id = proof.make_run_id(proof.manifest_sha256(data_dir), proof.snapshot_end(data_dir))
    path = tmp_path / "proof.json"
    proof.write_proof(path, {"run_id": run_id, "opentimestamps": {"status": "pending"}})
    rec = commit_flow(FakeChain(), data_dir, path)
    assert rec["opentimestamps"] == {"status": "pending"}


def test_commit_drops_the_stamp_of_an_older_manifest(data_dir, tmp_path) -> None:
    """A stamp belongs to one manifest; keeping it beside a newer commit would mislabel it."""
    path = tmp_path / "proof.json"
    old = "capture-ledger-2026-10-25-aaaaaaaaaaaa"
    proof.write_proof(path, {"run_id": old, "opentimestamps": {"status": "confirmed"}})
    rec = commit_flow(FakeChain(), data_dir, path)
    assert "opentimestamps" not in rec and rec["run_id"] != old


def test_commit_fails_when_the_chain_does_not_show_the_hash_afterwards(data_dir, tmp_path) -> None:
    chain = FakeChain()
    chain.run = lambda argv: (
        0,
        f"Transaction ID: {TX}\n",
    )  # the CLI claims success, nothing stored
    with pytest.raises(proof.ProofError, match="does not show"):
        commit_flow(chain, data_dir, tmp_path / "proof.json")
    assert not (tmp_path / "proof.json").exists()


def test_commit_reports_a_failing_cli_and_never_echoes_the_key(data_dir, tmp_path) -> None:
    chain = FakeChain()
    chain.run = lambda argv: (1, "error: not enough balance\n")
    with pytest.raises(proof.ProofError) as err:
        commit_flow(chain, data_dir, tmp_path / "proof.json", private_key="ed25519:SECRETKEY")
    assert "not enough balance" in str(err.value) and "SECRETKEY" not in str(err.value)


def test_commit_asks_for_the_tx_when_it_cannot_read_it(data_dir, tmp_path) -> None:
    chain = FakeChain()
    chain.run = lambda argv: (setattr(chain, "committed", HASH_FOR(data_dir)), (0, "ok\n"))[1]
    with pytest.raises(proof.ProofError, match="--tx"):
        commit_flow(chain, data_dir, tmp_path / "proof.json")
    rec = commit_flow(chain, data_dir, tmp_path / "proof.json", tx_hash=TX)
    assert rec["near"]["tx_hash"] == TX


def HASH_FOR(data_dir) -> str:
    return proof.manifest_sha256(data_dir)


def test_get_reports_an_account_without_a_contract_instead_of_crashing() -> None:
    """Real testnet reply to a view call on an account with no code (HTTP 200, no result list)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return rpc_result(
            {
                "block_hash": "9jzQzyNkRdSmVTDmyjTMwsiFuvsNcXPDwFHLdy5jyax1",
                "block_height": 276016635,
                "error": "wasm execution failed with error: CompilationError(CodeDoesNotExist "
                '{ account_id: "nepu-ledger.testnet" })',
                "logs": [],
            }
        )

    with pytest.raises(proof.ProofError, match="CodeDoesNotExist"):
        proof.get(rpc_client(handler), "https://rpc.example", CONTRACT, "run-1")
