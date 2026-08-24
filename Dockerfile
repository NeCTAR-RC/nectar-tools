FROM python:3.14-slim-trixie

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Running pip as root is expected inside the image build
ENV PIP_ROOT_USER_ACTION=ignore

# Install pip requirements. gcc is only needed to build wheels during the
# install, so install it, build, then purge it and the apt cache so the
# compiler is not left in the runtime image.
COPY requirements.txt .

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && python -m pip install --no-cache-dir \
        -c https://releases.openstack.org/constraints/upper/2026.1 \
        -r requirements.txt \
    && apt-get purge -y --auto-remove gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY dist/* /app

RUN python -m pip install --no-cache-dir \
        -c https://releases.openstack.org/constraints/upper/2026.1 \
        *.tar.gz \
    && rm *.tar.gz

# Creates a non-root user and adds permission to access the /app folder
RUN useradd -u 42420 appuser && chown -R appuser /app
USER appuser

# The tools are one-shot commands run by cron or a CronJob spec, which
# supplies the real command (nectar-allocation-expiry, nectar-coe-audit,
# etc). Config is expected at /etc/nectar/tools.ini.
CMD ["nectar-allocation-audit", "--help"]
