# =========================
# configuration
# =========================
RESULT_DIR="${HOME}/va_results"
IMAGE="periodic_bench:test"
CPU_RT="3"
OTHER_CPUS="0-2,4-10,12-15"

PERIOD="5000000"
DEADLINE="3000000"
DURATION="500"

# VC4-S (cpu.shares / indirect multi-tenant; dedicated CPU 3)
HOG_IMAGE="alpine"
HOG_SHARES=2048
HOG_MAX=12
HOG_PREFIX="hog"

# Shares of benchmark and hogs
BENCH_SHARES=1024
SHARED_POOL_N=12  
HOG_SHARES=256
SHARED_CPUS="3,4,5,6,7,8,9,10,11,12,13,14"


