FROM debian:bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN make clean && make

FROM debian:bookworm
WORKDIR /app
COPY --from=builder /app/periodic_bench /app/periodic_bench
CMD ["./periodic_bench", "--help"]