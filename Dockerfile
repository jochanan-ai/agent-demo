# agent-demo: standard library only. Runs on the staging VM under gVisor, read-only, as 10001
# (asome-platform vms/staging/app-compose.yaml.j2 sets the hardening; Renovate pins the digest).
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
COPY app /opt/app/app
ENV PYTHONPATH=/opt/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
USER 10001:10001
EXPOSE 8080
CMD ["python3", "-m", "app.server"]
