FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SINGULAR_ROOT=/var/lib/singular

RUN groupadd --system singular && useradd --system --gid singular --home /var/lib/singular singular
WORKDIR /opt/singular
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY configs /etc/singular
RUN python -m pip install . && \
    install -d -o singular -g singular /var/lib/singular /var/lib/singular/mem \
      /var/lib/singular/runs /var/lib/singular/lives /etc/singular

USER singular:singular
VOLUME ["/var/lib/singular/mem", "/var/lib/singular/runs", "/var/lib/singular/lives", "/etc/singular"]
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "from pathlib import Path; import sys; c=Path('/proc/1/cmdline').read_bytes(); sys.exit(0 if b'singular' in c and b'orchestrate' in c else 1)"]
CMD ["singular", "orchestrate", "run", "--lifecycle-config", "/etc/singular/lifecycle.yaml"]
