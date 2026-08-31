CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -Wpedantic -std=c11

.PHONY: all clean
all: periodic_bench
periodic_bench: periodic_bench.c
	$(CC) $(CFLAGS) -o $@ $<
clean:
	rm -f periodic_bench
