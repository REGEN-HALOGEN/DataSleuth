#!/bin/sh
set -eu

umask 077
printf '%s' "${DATASLEUTH_DB_CA_B64:?Set the Supabase database CA}" | base64 -d > /tmp/supabase-ca.crt
exec python -m app.serve
