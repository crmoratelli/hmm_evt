# ===== Compiler and flags =====
CC      := gcc
CFLAGS  := -O2 -Wall -Wextra -Wpedantic -std=gnu11
LDFLAGS := -pthread -lrt

# ===== Target =====
TARGET  := periodic_bench
SRC     := periodic_bench.c
OBJ     := $(SRC:.c=.o)

# ===== Default =====
all: $(TARGET)

# ===== Build =====
$(TARGET): $(OBJ)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

# ===== Utilities =====
clean:
	rm -f $(TARGET) *.o

distclean: clean

.PHONY: all clean distclean

