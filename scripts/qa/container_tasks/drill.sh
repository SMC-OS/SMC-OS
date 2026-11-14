set -u
say() { echo "DRILL|$*"; }
rm -rf /tmp/qa-drill-src && mkdir -p /tmp/qa-drill-src
[ -n "${QA_TASK_TGZ_B64:-}" ] || { say "FAILED bundle missing"; exit 1; }
echo "$QA_TASK_TGZ_B64" | base64 -d | tar -xz -C /tmp/qa-drill-src || { say "FAILED bundle unpack"; exit 1; }
cd /app && python /tmp/qa-drill-src/scripts/qa/qa_recovery_drill.py
rc=$?
rm -rf /tmp/qa-drill-src
exit $rc
