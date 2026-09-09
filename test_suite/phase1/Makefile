CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -Wpedantic -std=c11
all: periodic_v2
periodic_v2: periodic_v2.c
	$(CC) $(CFLAGS) -pthread -o $@ $<
clean:
	rm -f periodic_v2
.PHONY: all clean
