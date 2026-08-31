#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s PKG APPLE_TEAM_ID SIGNER_SUBJECT OUTPUT_JSON\n' "${0##*/}" >&2
  exit 2
}

[[ $# -eq 4 ]] || usage
pkg=$1
team_id=$2
signer_subject=$3
output=$4

[[ $team_id =~ ^[A-Z0-9]{10}$ ]] || { echo 'ERROR: invalid Apple Team ID' >&2; exit 1; }
[[ -f $pkg && ! -L $pkg ]] || { echo 'ERROR: PKG must be a regular non-symlink file' >&2; exit 1; }
[[ ${pkg##*/} == Sinbar-Support-Assistant.pkg ]] || { echo 'ERROR: unexpected PKG filename' >&2; exit 1; }

for tool in pkgutil spctl xcrun shasum python3; do
  command -v "$tool" >/dev/null || { echo "ERROR: required tool missing: $tool" >&2; exit 1; }
done

signature_output=$(pkgutil --check-signature "$pkg" 2>&1)
printf '%s\n' "$signature_output"
grep -Fq "$team_id" <<<"$signature_output" || { echo 'ERROR: installer Team ID mismatch' >&2; exit 1; }
grep -Fiq "$signer_subject" <<<"$signature_output" || { echo 'ERROR: installer signer subject mismatch' >&2; exit 1; }

xcrun stapler validate "$pkg"
spctl --assess --type install --verbose=4 "$pkg"

digest=$(shasum -a 256 "$pkg" | awk '{print $1}')
verified_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

PKG_SHA256=$digest VERIFIED_AT=$verified_at TEAM_ID=$team_id SIGNER_SUBJECT=$signer_subject OUTPUT=$output \
python3 - <<'PY'
import json
import os
from pathlib import Path

document = {
    "schemaVersion": 1,
    "platform": "macos",
    "artifact": "Sinbar-Support-Assistant.pkg",
    "sha256": os.environ["PKG_SHA256"],
    "verifiedAt": os.environ["VERIFIED_AT"],
    "gatekeeperAccepted": True,
    "installerTeamIdentifier": os.environ["TEAM_ID"],
    "notarizationStapled": True,
    "pkgSignatureValid": True,
    "signerSubject": os.environ["SIGNER_SUBJECT"],
}
Path(os.environ["OUTPUT"]).write_text(
    json.dumps(document, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

echo 'PASS: macOS Developer ID Installer signature, notarization staple, and Gatekeeper acceptance verified.'
