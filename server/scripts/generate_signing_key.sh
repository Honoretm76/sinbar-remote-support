#!/usr/bin/env sh
set -eu

umask 077
destination="${1:-manifest-ecdsa-p256.pem}"

if [ -e "$destination" ]; then
    printf 'Refusing to overwrite %s\n' "$destination" >&2
    exit 1
fi

openssl ecparam -name prime256v1 -genkey -noout -out "$destination"
chmod 0600 "$destination"
printf 'Created ECDSA P-256 private key: %s\n' "$destination"
printf 'Keep this file outside the image and back it up securely.\n'

