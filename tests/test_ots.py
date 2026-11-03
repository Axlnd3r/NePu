"""OpenTimestamps entry of proof.json: parsing `ots info` and recording it.

The pending sample is the real output of `ots info` from the CI run that stamped the manifest
(opentimestamps-client 0.8.0), trimmed to its first lines and its attestation lines. The
Bitcoin line below follows the client's known format and is confirmed by the first real upgrade.
"""

import json

import pytest

from capture import build, proof

HASH = "48c59060cee309e2aafb62614dfb24454828bf5ae8f534bd52154165b5b8c096"
RUN_ID = "capture-ledger-2026-11-01-48c59060cee3"

PENDING = f"""File sha256 hash: {HASH}
Timestamp:
append 6577e34842a7f9f09a47657fd27d337f
sha256
 -> append 831b7b8d55537c287c698bceb47e0f66
    sha256
    prepend 6ae98e95
    append bcc3151251548179
    verify PendingAttestation('https://finney.calendar.eternitywall.com')
 -> append b49270dc218a5a2b
    sha256
    verify PendingAttestation('https://bob.btc.calendar.opentimestamps.org')
 -> append c1fa9749cb9fac7b
    sha256
    verify PendingAttestation('https://alice.btc.calendar.opentimestamps.org')
 -> append d73fceee82ac4d7e237685f11a3b72e2
    sha256
    verify PendingAttestation('https://btc.calendar.catallaxy.com')
"""

CONFIRMED = PENDING.replace(
    "verify PendingAttestation('https://bob.btc.calendar.opentimestamps.org')",
    "verify BitcoinBlockHeaderAttestation(358391)",
)


def test_a_fresh_stamp_is_pending_at_four_calendars() -> None:
    info = proof.parse_ots_info(PENDING)
    assert info["status"] == "pending"
    assert info["file_sha256"] == HASH
    assert info["bitcoin_blocks"] == []
    assert info["pending_calendars"] == [
        "https://finney.calendar.eternitywall.com",
        "https://bob.btc.calendar.opentimestamps.org",
        "https://alice.btc.calendar.opentimestamps.org",
        "https://btc.calendar.catallaxy.com",
    ]


def test_a_bitcoin_attestation_makes_the_stamp_confirmed() -> None:
    info = proof.parse_ots_info(CONFIRMED)
    assert info["status"] == "confirmed" and info["bitcoin_blocks"] == [358391]
    assert len(info["pending_calendars"]) == 3  # the others may still be pending


def test_output_without_attestations_is_unknown_not_pending() -> None:
    assert proof.parse_ots_info("error: not a timestamp file\n")["status"] == "unknown"


def make_proof(tmp_path, ots_text: str | None = "stub") -> tuple:
    path = tmp_path / "proof.json"
    near = proof.near_record("testnet", "c.testnet", "c.testnet", RUN_ID, "Tx1", 5)
    proof.write_proof(path, {"run_id": RUN_ID, "manifest_sha256": HASH, "near": near})
    if ots_text is not None:
        d = tmp_path / "proof" / RUN_ID
        d.mkdir(parents=True)
        (d / "manifest.json.ots").write_bytes(b"\x00")
    return path


def test_recording_adds_the_stamp_and_keeps_the_near_entry(tmp_path) -> None:
    path = make_proof(tmp_path)
    seen = []

    def run(argv):
        seen.append(argv)
        return 0, PENDING

    rec = proof.ots_record(path, run)
    assert seen[0][:2] == ["ots", "info"] and seen[0][2].endswith("manifest.json.ots")
    ots = rec["opentimestamps"]
    assert ots["status"] == "pending" and ots["file_sha256"] == HASH
    assert ots["proof_file"] == f"data/proof/{RUN_ID}/manifest.json.ots"
    assert rec["near"]["tx_hash"] == "Tx1"
    assert proof.read_proof(path) == rec


def test_recording_refuses_a_stamp_of_another_file(tmp_path) -> None:
    path = make_proof(tmp_path)
    with pytest.raises(proof.ProofError, match="another file"):
        proof.ots_record(path, lambda argv: (0, PENDING.replace(HASH, "0" * 64)))


def test_recording_needs_the_stamp_file(tmp_path) -> None:
    path = make_proof(tmp_path, ots_text=None)
    with pytest.raises(proof.ProofError, match="manifest.json.ots"):
        proof.ots_record(path, lambda argv: (0, PENDING))


def test_recording_reports_a_failing_ots(tmp_path) -> None:
    path = make_proof(tmp_path)
    with pytest.raises(proof.ProofError, match="ots info failed"):
        proof.ots_record(path, lambda argv: (1, "boom"))


def test_the_site_shows_the_stamp_status_and_how_to_get_the_file(tmp_path) -> None:
    path = make_proof(tmp_path)
    proof.ots_record(path, lambda argv: (0, PENDING))
    status = proof.site_status(proof.read_proof(path), HASH)
    assert status["opentimestamps"]["status"] == "pending"
    assert status["opentimestamps"]["file"] == "data/proof/manifest.json.ots"


def test_the_site_has_no_stamp_entry_before_one_exists(tmp_path) -> None:
    path = make_proof(tmp_path, ots_text=None)
    assert proof.site_status(proof.read_proof(path), HASH)["opentimestamps"] is None


def test_build_serves_the_ots_file_byte_for_byte(tmp_path) -> None:
    written = {p.name: p for p in build.build("snapshot", tmp_path)}
    stamp = build.REFERENCE.parent / "proof" / json.loads(build.PROOF_FILE.read_text())["run_id"]
    assert written["manifest.json.ots"].read_bytes() == (stamp / "manifest.json.ots").read_bytes()
