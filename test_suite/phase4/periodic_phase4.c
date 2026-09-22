#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <sched.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>

static uint64_t now_ns(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) { perror("clock_gettime"); exit(1); }
    return (uint64_t)t.tv_sec * 1000000000ULL + (uint64_t)t.tv_nsec;
}

static void sleep_until(uint64_t ns) {
    struct timespec t = {(time_t)(ns / 1000000000ULL), (long)(ns % 1000000000ULL)};
    int rc;
    do { rc = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &t, NULL); } while (rc == EINTR);
    if (rc) { fprintf(stderr, "clock_nanosleep: %s\n", strerror(rc)); exit(1); }
}

static void payload(uint64_t iters) {
    volatile double x = 1.0;
    for (uint64_t i = 0; i < iters; ++i) x = x * 1.0000001 + 0.0000001;
    (void)x;
}

static uint64_t number(const char *s) {
    char *end = NULL;
    errno = 0;
    unsigned long long n = strtoull(s, &end, 10);
    if (errno || !*s || *s == '-' || *end) {
        fprintf(stderr, "invalid integer: %s\n", s);
        exit(2);
    }
    return (uint64_t)n;
}

int main(int argc, char **argv) {
    uint64_t period = 5000000, deadline = 5000000, jobs = 300, iters = 0;
    uint64_t shock_job = 100, shock_ns = 0;
    const char *out = NULL;
    bool lock_memory = false;

    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i];
        if (!strcmp(a, "--mlock")) { lock_memory = true; continue; }
        if (!strcmp(a, "--version")) {
            puts("TDPS phase4 schema=1 controlled-block fixed-jobs");
            return 0;
        }
        if (i + 1 == argc) { fprintf(stderr, "missing value: %s\n", a); return 2; }
        const char *v = argv[++i];
        if (!strcmp(a, "--out")) out = v;
        else if (!strcmp(a, "--period")) period = number(v);
        else if (!strcmp(a, "--deadline")) deadline = number(v);
        else if (!strcmp(a, "--jobs")) jobs = number(v);
        else if (!strcmp(a, "--iters")) iters = number(v);
        else if (!strcmp(a, "--shock-job")) shock_job = number(v);
        else if (!strcmp(a, "--shock-ns")) shock_ns = number(v);
        else { fprintf(stderr, "unknown option: %s\n", a); return 2; }
    }

    if (!out || !period || !deadline || !jobs || !iters || jobs > 1000000 ||
        shock_job >= jobs || shock_ns > 1000000000ULL ||
        period > UINT64_MAX / jobs || deadline > INT64_MAX) {
        fprintf(stderr, "invalid configuration\n");
        return 2;
    }
    if (lock_memory && mlockall(MCL_CURRENT | MCL_FUTURE)) { perror("mlockall"); return 1; }

    FILE *csv = fopen(out, "wx");
    if (!csv) { perror("fopen output"); return 1; }
    fprintf(csv, "schema_version,job,release_ns,start_ns,compute_finish_ns,block_start_ns,block_finish_ns,finish_ns,wakeup_delay_ns,compute_ns,block_actual_ns,response_ns,lateness_ns,miss,cpu,shock_requested_ns\n");

    struct sched_param sp = {0};
    sched_getparam(0, &sp);
    fprintf(stderr, "schema=1 jobs=%" PRIu64 " period=%" PRIu64 " deadline=%" PRIu64
            " iters=%" PRIu64 " shock_job=%" PRIu64 " shock_ns=%" PRIu64
            " policy=%d priority=%d cpu=%d mlock=%d\n",
            jobs, period, deadline, iters, shock_job, shock_ns,
            sched_getscheduler(0), sp.sched_priority, sched_getcpu(), lock_memory);

    const uint64_t epoch = now_ns() + 10000000ULL;
    for (uint64_t j = 0; j < jobs; ++j) {
        const uint64_t release = epoch + j * period;
        sleep_until(release);
        const uint64_t start = now_ns();
        payload(iters);
        const uint64_t compute_finish = now_ns();
        uint64_t block_start = compute_finish, block_finish = compute_finish;
        const uint64_t requested = (j == shock_job) ? shock_ns : 0;
        if (requested) {
            block_start = now_ns();
            sleep_until(block_start + requested);
            block_finish = now_ns();
        }
        const uint64_t finish = block_finish;
        const uint64_t response = finish - release;
        const int64_t lateness = (int64_t)response - (int64_t)deadline;
        fprintf(csv, "1,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64
                ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64
                ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRId64
                ",%d,%d,%" PRIu64 "\n",
                j, release, start, compute_finish, block_start, block_finish, finish,
                start - release, compute_finish - start, block_finish - block_start,
                response, lateness, lateness > 0, sched_getcpu(), requested);
    }
    if (ferror(csv) || fclose(csv)) { perror("write output"); return 1; }
    return 0;
}
