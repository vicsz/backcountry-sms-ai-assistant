#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <lambda-function-name> <configured-test-sender>" >&2
  exit 2
fi

function_name="$1"
test_sender="$2"
case "$function_name" in
  BackcountrySmsEchoTest-*) ;;
  *)
    echo "refusing to invoke a non-test Lambda target" >&2
    exit 1
    ;;
esac

configuration="$(aws lambda get-function-configuration \
  --function-name "$function_name" \
  --query 'Environment.Variables' \
  --output json)"
if ! jq -e '
  .DEPLOYMENT_ENVIRONMENT == "test" and
  .TEST_MODE == "true" and
  .SMS_DELIVERY_MODE == "capture"
' >/dev/null <<<"$configuration"; then
  echo "refusing to invoke a Lambda without test capture configuration" >&2
  exit 1
fi

fixture="tests/fixtures/stage-8-1-toronto.json"
temporary_payload="$(mktemp)"
temporary_response="$(mktemp)"
trap 'rm -f "$temporary_payload" "$temporary_response"' EXIT

jq --arg sender "$test_sender" \
  '.Records[0].Sns.Message |= (fromjson | .originationNumber = $sender | .destinationNumber = "stage-8-1-test-bot" | tojson)' \
  "$fixture" > "$temporary_payload"

aws lambda invoke \
  --function-name "$function_name" \
  --invocation-type RequestResponse \
  --payload "fileb://$temporary_payload" \
  "$temporary_response" >/dev/null

cat "$temporary_response"
