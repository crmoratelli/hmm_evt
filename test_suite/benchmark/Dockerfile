FROM ubuntu:24.04
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends util-linux ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY periodic_bench /usr/local/bin/periodic_bench
ENTRYPOINT ["/usr/local/bin/periodic_bench"]
