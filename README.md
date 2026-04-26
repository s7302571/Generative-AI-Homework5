# EIP-55 Address Checker in ETH — Homework 5

A skill that validates Ethereum addresses against the EIP-55
mixed-case checksum standard, shows which characters are miscased, and
optionally normalizes any-case input into its canonical EIP-55 form.

## What the skill does

Given an Ethereum address, the skill:

1. Checks the **format** — that the input is exactly 40 hex characters (after
   the optional `0x` prefix) and contains only `[0-9a-fA-F]`.
2. Checks the **EIP-55 checksum** — derives the canonical mixed-case form by
   keccak-256-hashing the lowercase address and re-casing each hex character
   based on the corresponding nibble of the hash.
3. Reports the result in one of three modes:
   - `validate` (default) — format + checksum status.
   - `diff` — adds a position-by-position comparison vs. the canonical form,
     marking each mismatched character with `^`.
   - `normalize` — prints the canonical EIP-55 form of the input (case-only
     transformation; does not "fix" wrong hex characters).

## Why I chose it

EIP-55 is a small, well-defined spec that solves a concrete, real problem:
Ethereum addresses are case-insensitive at the protocol level, but a single
mistyped character means funds go to the wrong place. The mixed-case checksum
catches roughly 99.986% of single-character typos, so wallets, block
explorers, and docs all rely on it — yet plenty of tooling still emits
all-lowercase addresses, leaving humans to eyeball the casing.

It's also a good fit for a skill specifically (rather than asking the model
directly) because the validation requires a **real keccak-256 hash**. LLMs
cannot compute cryptographic hashes reliably from memory, so without a script
the answer would be a confident guess. Wrapping a small Python script in a
skill lets Claude answer correctly every time, with a clear contract on what
inputs are valid and what the output looks like.

## How to use it

The skill triggers automatically when you ask Claude things like:

- "Is `0x26d3681DfC9E4c8C79cfbf461adec8A21d5d73C5` a valid ETH address?"

You can also run the underlying script directly:

```
python3 .claude/skills/eip55-address-checker/scripts/eip55.py validate <address>
python3 .claude/skills/eip55-address-checker/scripts/eip55.py diff     <address>
python3 .claude/skills/eip55-address-checker/scripts/eip55.py normalize <address>
```

The `0x` prefix is optional. The mode argument is optional and defaults to
`validate`.

## What the script does

`scripts/eip55.py` is a single-file Python 3 program with no required
third-party dependencies. It:

- Picks a keccak-256 backend at runtime: pycryptodome → eth-utils → a
  vendored pure-Python keccak-256 fallback. It deliberately does **not** fall
  back to `hashlib.sha3_256` (which is NIST SHA-3, with different padding —
  using it would silently produce wrong checksums).
- Validates the input format (length, prefix, hex character set).
- Computes the canonical EIP-55 form per the spec: hash the lowercase
  address, then for each hex character of the address, uppercase it iff the
  corresponding nibble of the hash is `>= 8`.
- Compares the input against the canonical form character-by-character and
  prints a structured report.
- Treats all-lowercase / all-uppercase input as "no checksum to verify"
  (correct per EIP-55) rather than flagging it as invalid.

## Test cases (from Step 5)

Three addresses were used to exercise the skill end-to-end through the agent:

| File | Address | Expected | Result |
|---|---|---|---|
| `normal-case.txt`     | `0x26d3681DfC9E4c8C79cfbf461adec8A21d5d73C5`     | valid checksum            | ✅ valid |
| `non-eip55-case.txt`  | `0x626f6d626f72612e6275696c6420f09f8c8a`         | format failure (36 chars) | ✅ rejected before checksum check |
| `edge-case.txt`       | `0x26d3681DfC9E4c8C79cfbf461adec8A21d5d73c5`     | invalid checksum (last `c5` should be `C5`) | ✅ flagged; canonical form returned |

A few notes on what each case is testing:

- **Normal case** — the happy path. A real, correctly-checksummed address
  should pass cleanly with no warnings.
- **Non-EIP-55 case** — a 36-hex-character string that *looks* like an
  address but is actually the UTF-8 bytes for `bombora.build 🌊`
  hex-encoded. Useful for confirming the format check fires *before* the
  checksum check, so a malformed input doesn't get a misleading "checksum
  invalid" result.
- **Edge case** — the canonical address with a single character re-cased
  (`C5` → `c5`). This is the most realistic real-world failure mode (a
  copy/paste casing slip) and verifies that the diff/canonical output is
  precise enough to point at the exact offending character.

## What worked well

- **Backend auto-selection** kept the script dependency-free for grading
  while still using a fast native keccak when one is installed.
- **Separating format checks from checksum checks** made the output much
  more useful — the non-EIP-55 case fails with "wrong length" instead of a
  confusing "checksum invalid", which would have been technically true but
  unhelpful.
- **Returning the canonical form on failure** turns a "no" answer into an
  actionable one: the user can immediately see what the address *should*
  look like and decide whether it was a casing typo or a hex typo.
- **Refusing to silently fix failing checksums** in the skill instructions
  matches how real wallet UIs behave and avoids the worst-case outcome
  (auto-"correcting" a mistyped hex character and sending funds to the
  wrong address).

## Limitations

- **EIP-55 only** — does not implement EIP-1191 (chain-ID-mixed checksums
  used by RSK, Ethereum Classic, etc.). An RSK address will be reported as
  failing even if it is correctly checksummed for its chain.
- **No ENS resolution** — `vitalik.eth` and other ENS names are not
  resolved; this skill only operates on raw hex addresses.
- **No key derivation** — does not derive addresses from public keys,
  private keys, or mnemonics.
- **One address per invocation** — batch audits require calling the script
  once per address and aggregating results.
- **Case-only normalization** — `normalize` mode changes case but never
  changes the underlying hex characters, so it is not a typo-correction
  tool. If the hex itself is wrong, the canonical output will also be wrong.
- **Mainnet-style assumption** — no chain ID is mixed into the hash, so
  results are only meaningful for chains that follow the original EIP-55.
