FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends util-linux && rm -rf /var/lib/apt/lists/*
COPY periodic_v2 /usr/local/bin/periodic_v2
ENTRYPOINT ["/usr/local/bin/periodic_v2"]
