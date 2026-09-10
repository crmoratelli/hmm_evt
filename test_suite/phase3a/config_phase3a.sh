#!/usr/bin/env bash

# Phase 3A: paired causal pilot, host + inline under identical I/O stress.
PHASE3A_RESULT_ROOT="${PHASE3A_RESULT_ROOT:-/home/ghost/tdps_phase3a_results}"
PHASE3A_TMPFS_ROOT="${PHASE3A_TMPFS_ROOT:-/dev/shm/tdps-phase3a}"
PHASE3A_REPLICATIONS="${PHASE3A_REPLICATIONS:-5}"
PHASE3A_SEED="${PHASE3A_SEED:-20260910}"

# The shared-path sink is on the same ext4 filesystem stressed through /tmp.
PHASE3A_EXT4_SINK_ROOT="${PHASE3A_EXT4_SINK_ROOT:-${PHASE3A_RESULT_ROOT}/runs}"

# Fixed scientific configuration inherited from phase 1.
PHASE3A_MODE="inline"
PHASE3A_SCENARIO="io"
PHASE3A_SUBSTRATE="host"
PHASE3A_SOURCE_SHA256="b9f64037c63540de421a8b39449a1f21fbf1043280ac8f12a3496511b4576cb2"

