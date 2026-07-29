# eda-pcb-designer — pipeline-in-a-box.
#
# Ships everything the full pipeline needs: KiCad 9 (kicad-cli + pcbnew +
# symbol libraries), Java 21 (freerouting), poppler (PDF→PNG renders) and
# the checksum-verified freerouting JAR. The repo itself is baked into
# /app, so the MT1 worked example runs out of the box:
#
#   docker build -t eda-pcb-designer .
#   docker run --rm -w /app eda-pcb-designer validate --config examples/mt1.yaml
#   docker run --rm -w /app eda-pcb-designer pipeline --config examples/mt1.yaml --stages place,render
#
# To work on your own board, bind-mount your repo over /work (the default
# workdir): docker run --rm -v "$PWD":/work eda-pcb-designer validate --config <yaml>
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

# Fetch the pinned freerouting JAR in its own layer (64 MB, checksum-verified)
# so repo edits don't re-download it.
COPY vendor/fetch-freerouting.sh /app/vendor/fetch-freerouting.sh
RUN /app/vendor/fetch-freerouting.sh

COPY . /app

# --system-site-packages so the venv can also see KiCad's pcbnew module
# (needed by the route stage's DSN/SES round-trip).
RUN python3 -m venv --system-site-packages /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir '/app[schematic,render,verify]'
ENV PATH=/opt/venv/bin:$PATH

# kicad-cli and the DIM-theme installer both write under $HOME/.config.
RUN useradd --create-home runner && chown -R runner /app
USER runner
ENV HOME=/home/runner

WORKDIR /work
ENTRYPOINT ["pcb-designer"]
CMD ["--help"]
