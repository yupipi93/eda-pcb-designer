# pcb-designer HTTP API — the image deployed to Cloud Run.
#
# Same toolchain as the root Dockerfile (KiCad 9 + Java 21 + freerouting +
# poppler) but serving the stateless HTTP API (src/pcb_designer/api.py) via
# gunicorn instead of the CLI. Built from the repo root:
#
#   docker build -f deploy/Dockerfile -t pcb-designer-api .
#   docker run --rm -p 8080:8080 pcb-designer-api
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      software-properties-common ca-certificates curl gpg-agent \
 && add-apt-repository -y ppa:kicad/kicad-9.0-releases \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      kicad kicad-symbols kicad-footprints \
      openjdk-21-jre-headless \
      poppler-utils fonts-dejavu-core \
      python3 python3-pip python3-venv \
 && rm -rf /var/lib/apt/lists/*

# Freerouting JAR in its own layer (64 MB, checksum-verified) so repo edits
# don't re-download it.
COPY vendor/fetch-freerouting.sh /app/vendor/fetch-freerouting.sh
RUN /app/vendor/fetch-freerouting.sh

COPY . /app

# --system-site-packages so the venv sees KiCad's pcbnew module (route endpoint).
RUN python3 -m venv --system-site-packages /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir '/app[api,render,verify]'
ENV PATH=/opt/venv/bin:$PATH

# kicad-cli writes under $HOME/.config; run non-root with a real home.
RUN useradd --create-home runner && chown -R runner /app
USER runner
ENV HOME=/home/runner
ENV PCB_DESIGNER_JAR=/app/vendor/freerouting.jar

# Cloud Run injects PORT (default 8080).
ENV PORT=8080
EXPOSE 8080

# pcbnew work is serialised behind an in-process lock, so keep it to ONE
# worker process; threads handle the subprocess-bound endpoints (drc/render/
# fab) concurrently. 300 s timeout covers freerouting on dense boards.
CMD exec gunicorn pcb_designer.api:app \
    --bind "0.0.0.0:${PORT}" \
    --workers 1 --threads 4 --timeout 300 \
    --access-logfile - --error-logfile -
