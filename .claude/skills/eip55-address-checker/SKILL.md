---
name: eip55-address-checker
description: Validates Ethereum addresses against the EIP-55 mixed-case checksum standard, identifies which characters have incorrect casing, and optionally normalizes a lowercase or any-case address into its canonical EIP-55 form. Use when the user asks to check, verify, audit, diff, or normalize an Ethereum address's checksum casing.
---

# EIP-55 Address Checker

## When to use this skill
- The user provides an Ethereum address and asks whether it is valid, correctly checksummed, or in the correct case.
- The user asks to compare an address against its expected EIP-55 form and see exactly which characters differ.
- The user asks to convert a lowercase, uppercase, or mixed-case Ethereum address into its canonical EIP-55 form.
- The user wants to audit a list of addresses for casing errors before sending funds, generating documentation, or storing them.

## When NOT to use this skill
- The address is for a non-EVM chain (Bitcoin, Solana, Cosmos, etc.) — EIP-55 does not apply.
- The user wants to validate an EIP-1191 chain-specific checksum (RSK, Ethereum Classic). This skill only implements the original EIP-55.
- The user wants to resolve an ENS name (e.g. `vitalik.eth`) to an address — that requires an RPC call.
- The user wants to derive an address from a private key, public key, or mnemonic.
- The user asks you to "fix" a failing checksum address by silently re-casing it. A checksum failure may signal a mistyped hex character, not just wrong case; silently re-casing could mask a typo that sends funds to the wrong place. Always report the failure first and let the user decide.

## Expected inputs
- A single Ethereum address string. The `0x` prefix is optional; the script handles both forms.
- An optional mode flag:
  - `validate` (default) — reports format validity and checksum status.
  - `diff` — when the checksum fails, shows a position-by-position comparison of the input vs. the canonical EIP-55 form, highlighting mismatched characters.
  - `normalize` — produces the canonical EIP-55 form from any-case input. Does not assert that the input was correct; it transforms it.

## Step-by-step instructions
1. Extract the address string from the user's request. If the user supplied multiple addresses, run the script once per address.
2. Decide the mode from the user's wording:
   - "is this checksum valid?", "verify", "check" → `validate`
   - "which characters are wrong?", "show me the diff" → `diff`
   - "convert to EIP-55", "give me the checksummed form", "normalize" → `normalize`
3. Invoke the script:
   ```
   python .claude/skills/eip55-address-checker/scripts/eip55.py <mode> <address>
   ```
4. Read the script's structured output and present it back to the user. Do not recompute or "double-check" the keccak-256 hash yourself — you cannot do this reliably. Trust the script.
5. If the script reports the checksum is invalid:
   - In `validate` mode, offer to re-run in `diff` mode to show the exact mismatched characters.
   - Warn the user that a checksum failure may indicate a typo in the hex characters themselves, not just wrong case. Recommend they double-check the source of the address before normalizing.
6. If the input is all-lowercase or all-uppercase, the script will report "no checksum to verify" — this is correct behavior, not an error. EIP-55 only validates mixed-case addresses.

## Expected output format
The skill returns a short structured report with these sections:

```
Address: 0x<input>
Format:
  - Length: <ok | wrong (got N, expected 42)>
  - Prefix: <0x present | 0x missing>
  - Hex characters: <ok | invalid characters at positions [...]>
Checksum:
  - Status: <valid | invalid | not applicable (all lowercase/uppercase)>
  - Canonical EIP-55: 0x<correctly-cased-form>
```

In `diff` mode, append:
```
Diff (^ marks mismatched positions):
  input:     0x<input>
  expected:  0x<canonical>
             <spaces and ^ markers>
Mismatches: <count> character(s) at positions [...]
```

In `normalize` mode, return only:
```
Address: 0x<input>
Canonical EIP-55: 0x<output>
```

## Important limitations and checks
- **Cryptographic correctness**: The script must use a real keccak-256 implementation (`eth_utils.keccak`, or `Crypto.Hash.keccak` from pycryptodome). Do **not** substitute `hashlib.sha3_256` — that is NIST SHA-3, which uses different padding and produces different output for the same input. The two are not interchangeable.
- **Input validation**: The script validates that the address is exactly 40 hex characters (excluding the `0x` prefix) and contains only `[0-9a-fA-F]`. Anything else fails fast with a clear error.
- **No silent fixes**: Even in `normalize` mode, the script preserves the underlying hex characters — it only changes case. If the hex itself is wrong, the canonical form will also be wrong; normalization is not a typo-correction tool.
- **Single chain assumption**: This skill assumes mainnet-style EIP-55. It does not mix in a chain ID, so it will report EIP-1191 addresses (RSK, ETC) as failing. If the user mentions those chains, stop and tell them this skill does not cover that variant.
- **One address at a time**: The script processes a single address per invocation. For batch audits, call it once per address and aggregate the results in your reply.
