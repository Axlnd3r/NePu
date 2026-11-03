//! Proof of analysis: stores `run_id -> manifest_sha256` pairs committed by the owner.
//!
//! A commit shows that a hash existed no later than the block of the transaction. It does not
//! show that the data behind the hash is correct. Entries are write-once. The contract holds and
//! moves no tokens and has no admin methods beyond the owner-only `commit`.

use near_sdk::store::LookupMap;
use near_sdk::{AccountId, PanicOnDefault, env, near, require};

const MAX_RUN_ID_BYTES: usize = 128;
const SHA256_HEX_LEN: usize = 64;

/// NEP-297 event log: `EVENT_JSON:{"standard":"proof_of_analysis","version":"1.0.0",...}`.
#[near(event_json(standard = "proof_of_analysis"))]
pub enum Event {
    #[event_version("1.0.0")]
    Commit {
        run_id: String,
        manifest_sha256: String,
    },
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct Contract {
    owner: AccountId,
    proofs: LookupMap<String, String>,
}

#[near]
impl Contract {
    #[init]
    pub fn new(owner: AccountId) -> Self {
        Self {
            owner,
            proofs: LookupMap::new(b"p".to_vec()),
        }
    }

    /// Store the pair and emit the event. Owner only; a `run_id` can be committed once.
    pub fn commit(&mut self, run_id: String, manifest_sha256: String) {
        let _ = (run_id, manifest_sha256);
        todo!("commit")
    }

    /// The hash committed under `run_id`, if any.
    pub fn get(&self, run_id: String) -> Option<String> {
        let _ = run_id;
        todo!("get")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use near_sdk::test_utils::{VMContextBuilder, get_logs};
    use near_sdk::{serde_json, testing_env};

    const OWNER: &str = "proof.test.near";
    const HASH: &str = "48c59060cee309e2aafb62614dfb24454828bf5ae8f534bd52154165b5b8c096";
    const OTHER_HASH: &str = "0000000000000000000000000000000000000000000000000000000000000001";

    fn as_caller(account: &str) {
        testing_env!(
            VMContextBuilder::new()
                .predecessor_account_id(account.parse().unwrap())
                .build()
        );
    }

    fn contract() -> Contract {
        as_caller(OWNER);
        Contract::new(OWNER.parse().unwrap())
    }

    #[test]
    fn commit_stores_the_pair_and_get_returns_it() {
        let mut c = contract();
        c.commit("run-1".to_string(), HASH.to_string());
        assert_eq!(c.get("run-1".to_string()), Some(HASH.to_string()));
    }

    #[test]
    fn get_returns_none_for_an_unknown_run() {
        let c = contract();
        assert_eq!(c.get("never-committed".to_string()), None);
    }

    #[test]
    fn two_runs_are_kept_apart_and_may_share_a_hash() {
        let mut c = contract();
        c.commit("run-1".to_string(), HASH.to_string());
        c.commit("run-2".to_string(), OTHER_HASH.to_string());
        c.commit("run-3".to_string(), HASH.to_string());
        assert_eq!(c.get("run-1".to_string()), Some(HASH.to_string()));
        assert_eq!(c.get("run-2".to_string()), Some(OTHER_HASH.to_string()));
        assert_eq!(c.get("run-3".to_string()), Some(HASH.to_string()));
    }

    #[test]
    fn commit_emits_a_nep_297_event_with_the_pair() {
        let mut c = contract();
        c.commit("run-1".to_string(), HASH.to_string());
        let logs = get_logs();
        assert_eq!(logs.len(), 1, "exactly one log line: {logs:?}");
        let json = logs[0]
            .strip_prefix("EVENT_JSON:")
            .expect("NEP-297 logs start with EVENT_JSON:");
        let event: serde_json::Value = serde_json::from_str(json).unwrap();
        assert_eq!(event["standard"], "proof_of_analysis");
        assert_eq!(event["version"], "1.0.0");
        assert_eq!(event["event"], "commit");
        assert_eq!(event["data"]["run_id"], "run-1");
        assert_eq!(event["data"]["manifest_sha256"], HASH);
    }

    #[test]
    #[should_panic(expected = "only the owner can commit")]
    fn a_non_owner_cannot_commit() {
        let mut c = contract();
        as_caller("mallory.near");
        c.commit("run-1".to_string(), HASH.to_string());
    }

    #[test]
    #[should_panic(expected = "run_id already committed")]
    fn a_run_id_cannot_be_committed_twice() {
        let mut c = contract();
        c.commit("run-1".to_string(), HASH.to_string());
        c.commit("run-1".to_string(), OTHER_HASH.to_string());
    }

    #[test]
    #[should_panic(expected = "manifest_sha256 must be 64 lowercase hex characters")]
    fn a_short_hash_is_rejected() {
        contract().commit("run-1".to_string(), HASH[..63].to_string());
    }

    #[test]
    #[should_panic(expected = "manifest_sha256 must be 64 lowercase hex characters")]
    fn a_long_hash_is_rejected() {
        contract().commit("run-1".to_string(), format!("{HASH}0"));
    }

    #[test]
    #[should_panic(expected = "manifest_sha256 must be 64 lowercase hex characters")]
    fn an_uppercase_hash_is_rejected() {
        contract().commit("run-1".to_string(), HASH.to_uppercase());
    }

    #[test]
    #[should_panic(expected = "manifest_sha256 must be 64 lowercase hex characters")]
    fn a_non_hex_hash_is_rejected() {
        contract().commit("run-1".to_string(), format!("g{}", &HASH[1..]));
    }

    #[test]
    #[should_panic(expected = "run_id must be 1 to 128 bytes")]
    fn an_empty_run_id_is_rejected() {
        contract().commit(String::new(), HASH.to_string());
    }

    #[test]
    #[should_panic(expected = "run_id must be 1 to 128 bytes")]
    fn an_overlong_run_id_is_rejected() {
        contract().commit("x".repeat(129), HASH.to_string());
    }

    #[test]
    fn the_longest_allowed_run_id_is_accepted() {
        let mut c = contract();
        let id = "x".repeat(128);
        c.commit(id.clone(), HASH.to_string());
        assert_eq!(c.get(id), Some(HASH.to_string()));
    }
}
