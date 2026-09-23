CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -Wpedantic -std=c11
TARGET := periodic_v2
SOURCE := ../phase1/periodic_v2.c

.PHONY: all clean
all: $(TARGET)
$(TARGET): $(SOURCE)
	$(CC) $(CFLAGS) -pthread -o $@ $<
clean:
	rm -f $(TARGET)

