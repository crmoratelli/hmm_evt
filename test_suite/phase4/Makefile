CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -Wpedantic -std=c11

all: periodic_phase4

periodic_phase4: periodic_phase4.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f periodic_phase4

.PHONY: all clean
