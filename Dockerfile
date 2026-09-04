FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 simo

COPY --chown=simo:simo app ./app
COPY --chown=simo:simo alembic ./alembic
COPY --chown=simo:simo alembic.ini ./

USER simo

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

# Sprint 033 (ADR-035): runs the migration gate (runtime check + the
# advisory-locked pending-migration step, see app/core/migrate_gate.py)
# before ever exec'ing uvicorn, so a failed migration means this
# container never binds its health-check port and is never promoted to
# serve traffic — guaranteed on every container start, independent of
# whether a separate deploy-hook step fires. `exec` hands PID 1 to
# uvicorn so shutdown signals reach it directly. To run only the
# migration (the previous "invoke the image as a release job" pattern),
# run `python -m app.core.migrate_gate` directly instead of this image's
# default command.
CMD ["sh", "-c", "python -m app.core.migrate_gate && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
