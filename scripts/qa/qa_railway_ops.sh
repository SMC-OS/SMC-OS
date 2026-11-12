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
# Evidence (probes A and B, 12 Nov): a failing step appended to the PRE-DEPLOY command still gave a SUCCESS
# deployment, so pre-deploy cannot be used or verified here. The START command runs for certain, with the service
# variables; if provisioning fails or the variables are missing the new container exits and the deployment FAILS
# (observable), while the previous deployment keeps serving.
QA_ORIG_START='sh -c '"'"'python -m app.core.migrate_gate && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log'"'"''
QA_PROVISION_START='sh -c '"'"'python -m app.core.migrate_gate && [ -n "$QA_PROVISION_SH_B64" ] && [ -n "$QA_PROVISION_PY_B64" ] && [ -n "$QA_OWNER_A_PW" ] && echo "$QA_PROVISION_SH_B64" | base64 -d | sh && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log'"'"''

gql() {  # gql '<query>' '<variables-json>'
  local body
  body="$(jq -nc --arg q "$1" --argjson v "${2:-{\}}" '{query:$q,variables:$v}')"
  curl -sS --max-time 40 "$QA_GQL" -H "Project-Access-Token: $RAILWAY_TOKEN" -H 'Content-Type: application/json' -d "$body"
}

svc_cmd_get() {  # svc_cmd_get preDeployCommand|startCommand
  gql 'query($s:String!,$e:String!){ serviceInstance(serviceId:$s, environmentId:$e){ startCommand preDeployCommand } }' \
    "$(jq -nc --arg s "$QA_API_SVC" --arg e "$QA_ENV" '{s:$s,e:$e}')" | jq -r --arg f "$1" '.data.serviceInstance[$f] | if type=="array" then .[0] else . end // empty'
}

svc_cmd_set() {  # svc_cmd_set startCommand '<command>'   (preDeployCommand takes a one-element list)
  local field="$1" out input
  if [[ "$field" == "preDeployCommand" ]]; then input="$(jq -nc --arg c "$2" '{preDeployCommand:[$c]}')"; else input="$(jq -nc --arg c "$2" '{startCommand:$c}')"; fi
  out="$(gql 'mutation($s:String!,$e:String!,$i:ServiceInstanceUpdateInput!){ serviceInstanceUpdate(serviceId:$s, environmentId:$e, input:$i) }' \
    "$(jq -nc --arg s "$QA_API_SVC" --arg e "$QA_ENV" --argjson i "$input" '{s:$s,e:$e,i:$i}')")"
  if [[ "$(jq -r '.errors // empty' <<<"$out")" != "" ]]; then
    echo "$field update refused: $(jq -c '[.errors[].message]' <<<"$out")"; return 1
  fi
}

predeploy_get() { svc_cmd_get preDeployCommand; }
predeploy_set() { svc_cmd_set preDeployCommand "$1"; }
start_get() { svc_cmd_get startCommand; }
start_set() { svc_cmd_set startCommand "$1"; }

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
# A value stored through the CLI may carry a trailing newline; it must never become part of a password.
clean() { printf '%s' "$1" | tr -d '\r\n'; }
echo "$QA_PROVISION_PY_B64" | base64 -d > /tmp/qa_provision.py
SYNTHETIC_OWNER_PASSWORD="$(clean "$QA_OWNER_A_PW")" python - --email "$(clean "$QA_OWNER_A_EMAIL")" --company "$(clean "$QA_OWNER_A_COMPANY")" --confirm-environment acceptance --idempotent --verify-login < /tmp/qa_provision.py
SYNTHETIC_OWNER_PASSWORD="$(clean "$QA_OWNER_B_PW")" python - --email "$(clean "$QA_OWNER_B_EMAIL")" --company "$(clean "$QA_OWNER_B_COMPANY")" --confirm-environment acceptance --idempotent --verify-login < /tmp/qa_provision.py
rm -f /tmp/qa_provision.py
SH
}

QA_TEMP_VARS=(QA_PROVISION_PY_B64 QA_PROVISION_SH_B64 QA_OWNER_A_EMAIL QA_OWNER_A_COMPANY QA_OWNER_A_PW QA_OWNER_B_EMAIL QA_OWNER_B_COMPANY QA_OWNER_B_PW)

set_qa_var() {  # set_qa_var KEY  (value on stdin; never on a command line)
  railway variable set "$1" --stdin --service geocore-api-qa --environment "$QA_ENV" --skip-deploys >/dev/null
}

remove_temp_vars() {
  # `railway variable delete` has no --skip-deploys flag: each delete starts a deployment, so callers must
  # wait_for_stable_success afterwards. Errors are reported, never swallowed.
  local k rc=0
  for k in "${QA_TEMP_VARS[@]}"; do
    railway variable delete "$k" --service geocore-api-qa --environment "$QA_ENV" >/dev/null 2>&1 || echo "delete $k: not present or failed"
  done
  railway variable list --service geocore-api-qa --environment "$QA_ENV" --json 2>/dev/null | jq -e 'keys | map(select(startswith("QA_"))) | length == 0' >/dev/null || rc=1
  return $rc
}

wait_for_stable_success() {  # latest deployment SUCCESS and unchanged for 60s; wait_for_stable_success [timeout-seconds]
  local deadline=$(( $(date +%s) + ${1:-900} )) last="" since=0 id status commit
  while (( $(date +%s) < deadline )); do
    read -r id status commit < <(latest_deployment)
    if [[ "$status" == "SUCCESS" ]]; then
      if [[ "$id" == "$last" ]]; then
        (( $(date +%s) - since >= 60 )) && { echo "stable deployment $id SUCCESS commit=$commit"; return 0; }
      else
        last="$id"; since=$(date +%s)
      fi
    else
      last=""
      [[ "$status" == "FAILED" || "$status" == "CRASHED" ]] && { echo "latest deployment $id is $status"; return 1; }
    fi
    sleep 10
  done
  echo "timed out waiting for a stable successful deployment"; return 1
}

wait_for_ready() {  # wait_for_ready <base-url> [timeout-seconds]; prints the status codes seen
  local deadline=$(( $(date +%s) + ${2:-240} )) code seen=""
  while (( $(date +%s) < deadline )); do
    code="$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' "$1/ready" 2>/dev/null || echo 000)"
    seen="$seen $code"
    [[ "$code" == "200" ]] && { echo "ready after:$seen"; return 0; }
    sleep 6
  done
  echo "not ready; saw:$seen"; return 1
}

deployment_log_summary() {  # deployment_log_summary <deployment-id>: only lines that cannot contain secrets
  local id="$1"
  for flag in --build --deployment; do
    echo "--- logs $flag"
    railway logs "$id" "$flag" --service geocore-api-qa --environment "$QA_ENV" --lines 400 2>&1 \
      | grep -E "QA_PROVISION|provision|already provisioned|REFUSED|Running upgrade|alembic|runtime_check|Traceback|Error|error|Uvicorn|startup|\(head\)" | cut -c1-220 | head -25 || true
  done
}

# The QA services track the branch that carries this workflow, so a deployment created by a configuration
# change builds the branch HEAD, which can be newer than the pinned candidate. That is acceptable only when
# nothing the API image or web build consumes differs from the candidate; this proves it instead of assuming.
QA_RUNTIME_PATHS=(app alembic alembic.ini requirements.txt Dockerfile apps packages package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json deploy)

commit_matches_candidate() {  # commit_matches_candidate <deployed-commit> <candidate-commit> (run inside a full clone)
  [[ "$1" == "$2" ]] && { echo "exact"; return 0; }
  git cat-file -e "$1^{commit}" 2>/dev/null || return 1
  git diff --quiet "$2" "$1" -- "${QA_RUNTIME_PATHS[@]}" && { echo "identical-runtime-tree"; return 0; }
  return 1
}
