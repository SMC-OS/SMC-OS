#!/usr/bin/env bash
# Helpers for the isolated QA environment (project geocore-qa-20261110 / environment acceptance).
# Used by .github/workflows/geocore-qa-acceptance.yml with a project-scoped RAILWAY_TOKEN only.
# `railway ssh` cannot be used: it needs an SSH key registered to a user or workspace, which a project
# token cannot create. Instead, provisioning runs as a one-off step of the QA API's own pre-deploy command
# (inside Railway's private network) and the original command is ALWAYS restored afterwards.
# Never prints variable values. Source this file; do not execute it.

QA_GQL="https://backboard.railway.com/graphql/v2"
QA_API_SVC="40d0cad3-0c01-467a-910e-6c9f818fd2bf"
QA_ENV="f948241d-446f-43ed-bff0-5d12decffd50"
QA_ORIG_PREDEPLOY='python -m app.core.runtime_check && alembic upgrade head && alembic current'

gql() {  # gql '<query>' '<variables-json>'
  local body
  body="$(jq -nc --arg q "$1" --argjson v "${2:-{\}}" '{query:$q,variables:$v}')"
  curl -sS --max-time 40 "$QA_GQL" -H "Project-Access-Token: $RAILWAY_TOKEN" -H 'Content-Type: application/json' -d "$body"
}

predeploy_get() {
  gql 'query($s:String!,$e:String!){ serviceInstance(serviceId:$s, environmentId:$e){ preDeployCommand } }' \
    "$(jq -nc --arg s "$QA_API_SVC" --arg e "$QA_ENV" '{s:$s,e:$e}')" | jq -r '.data.serviceInstance.preDeployCommand[0] // empty'
}

predeploy_set() {  # predeploy_set '<command>'
  local out
  out="$(gql 'mutation($s:String!,$e:String!,$c:[String!]){ serviceInstanceUpdate(serviceId:$s, environmentId:$e, input:{preDeployCommand:$c}) }' \
    "$(jq -nc --arg s "$QA_API_SVC" --arg e "$QA_ENV" --arg c "$1" '{s:$s,e:$e,c:[$c]}')")"
  if [[ "$(jq -r '.errors // empty' <<<"$out")" != "" ]]; then
    echo "pre-deploy update refused: $(jq -c '[.errors[].message]' <<<"$out")"; return 1
  fi
}

latest_deployment() {  # prints: <id> <status> <commit>
  railway deployment list --service geocore-api-qa --environment "$QA_ENV" --json --limit 5 \
    | jq -r 'sort_by(.createdAt) | last | "\(.id) \(.status) \(.meta.commitHash // "n/a")"'
}

wait_for_new_deployment() {  # wait_for_new_deployment <previous-id> [timeout-seconds]
  local prev="$1" deadline=$(( $(date +%s) + ${2:-720} )) id status commit
  while (( $(date +%s) < deadline )); do
    read -r id status commit < <(latest_deployment)
    if [[ "$id" != "$prev" ]]; then
      case "$status" in
        SUCCESS) echo "deployment $id SUCCESS commit=$commit"; return 0 ;;
        FAILED|CRASHED) echo "deployment $id $status commit=$commit"; return 1 ;;
      esac
    fi
    sleep 10
  done
  echo "timed out waiting for a new deployment"; return 1
}

provision_script_sh() {  # the script run by the pre-deploy step; reads its inputs from service variables
  cat <<'SH'
set -e
echo "$QA_PROVISION_PY_B64" | base64 -d > /tmp/qa_provision.py
SYNTHETIC_OWNER_PASSWORD="$QA_OWNER_A_PW" python - --email "$QA_OWNER_A_EMAIL" --company "$QA_OWNER_A_COMPANY" --confirm-environment acceptance --idempotent < /tmp/qa_provision.py
SYNTHETIC_OWNER_PASSWORD="$QA_OWNER_B_PW" python - --email "$QA_OWNER_B_EMAIL" --company "$QA_OWNER_B_COMPANY" --confirm-environment acceptance --idempotent < /tmp/qa_provision.py
rm -f /tmp/qa_provision.py
SH
}

QA_TEMP_VARS=(QA_PROVISION_PY_B64 QA_PROVISION_SH_B64 QA_OWNER_A_EMAIL QA_OWNER_A_COMPANY QA_OWNER_A_PW QA_OWNER_B_EMAIL QA_OWNER_B_COMPANY QA_OWNER_B_PW)

set_qa_var() {  # set_qa_var KEY  (value on stdin; never on a command line)
  railway variable set "$1" --stdin --service geocore-api-qa --environment "$QA_ENV" --skip-deploys >/dev/null
}

remove_temp_vars() {
  local k rc=0
  for k in "${QA_TEMP_VARS[@]}"; do
    railway variable delete "$k" --service geocore-api-qa --environment "$QA_ENV" --skip-deploys >/dev/null 2>&1 || true
  done
  railway variable list --service geocore-api-qa --environment "$QA_ENV" --json 2>/dev/null | jq -e 'keys | map(select(startswith("QA_"))) | length == 0' >/dev/null || rc=1
  return $rc
}
