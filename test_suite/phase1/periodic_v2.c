#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

/* Schema 2. Fixed 64-byte records: job ID uint64 little-endian + 56 'T'. */
struct sample {
    uint64_t release, start, compute_finish, output_start, output_finish;
    uint64_t delivery_start, delivery_finish;
    int accepted, dropped, delivery_errno, cpu;
    unsigned char record[64];
};
static struct sample *samples;
static size_t *queue, qcap;
static _Atomic size_t head, tail;
static _Atomic bool done, ready;
static int sink_fd, logger_cpu, logger_error;
static uint64_t logger_delay_ns;
static uint64_t now(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) { perror("clock_gettime"); exit(1); }
    return (uint64_t)t.tv_sec * 1000000000ULL + (uint64_t)t.tv_nsec;
}
static void sleep_until(uint64_t ns) {
    struct timespec t = {(time_t)(ns / 1000000000ULL), (long)(ns % 1000000000ULL)};
    int rc;
    do { rc = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &t, NULL); } while (rc == EINTR);
    if (rc) { fprintf(stderr, "sleep: %s\n", strerror(rc)); exit(1); }
}
static void payload(uint64_t iters) {
    volatile double x = 1.0;
    for (uint64_t i = 0; i < iters; ++i) x = x * 1.0000001 + 0.0000001;
    (void)x;
}
static void deliver(size_t job) {
    struct sample *s = &samples[job];
    s->delivery_start = now();
    size_t offset = 0;
    while (offset < sizeof(s->record)) {
        ssize_t n = write(sink_fd, s->record + offset, sizeof(s->record) - offset);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { s->delivery_errno = n < 0 ? errno : EIO; break; }
        offset += (size_t)n;
    }
    s->delivery_finish = now();
}
static void *logger(void *unused) {
    (void)unused;
    cpu_set_t cpus; CPU_ZERO(&cpus); CPU_SET(logger_cpu, &cpus);
    logger_error = pthread_setaffinity_np(pthread_self(), sizeof(cpus), &cpus);
    struct sched_param sp = {0};
    if (!logger_error) logger_error = pthread_setschedparam(pthread_self(), SCHED_OTHER, &sp);
    atomic_store_explicit(&ready, true, memory_order_release);
    if (logger_error) return NULL;
    for (;;) {
        size_t t = atomic_load_explicit(&tail, memory_order_relaxed);
        size_t h = atomic_load_explicit(&head, memory_order_acquire);
        if (t != h) {
            size_t job = queue[t % qcap];
            if (logger_delay_ns) sleep_until(now() + logger_delay_ns); /* test injection */
            deliver(job);
            /* Slot remains occupied until delivery completes. */
            atomic_store_explicit(&tail, t + 1, memory_order_release);
        } else {
            if (atomic_load_explicit(&done, memory_order_acquire)) {
                if (atomic_load_explicit(&head, memory_order_acquire) == t) break;
                continue;
            }
            sleep_until(now() + 100000); /* 100 us polling, no producer syscall */
        }
    }
    return NULL;
}
static uint64_t number(const char *s) {
    char *end; errno = 0;
    unsigned long long n = strtoull(s, &end, 10);
    if (errno || !*s || *s == '-' || *end) { fprintf(stderr, "invalid integer: %s\n", s); exit(2); }
    return n;
}
int main(int argc, char **argv) {
    uint64_t period=5000000, deadline=3000000, jobs=200, iters=0;
    uint64_t inject_job=UINT64_MAX, inject_ns=0;
    const char *mode="deferred", *out=NULL, *sink=NULL;
    bool lock_memory=false, minimal=false;
    qcap=1024; logger_cpu=-1;
    for (int i=1; i<argc; ++i) {
        const char *a=argv[i];
        if (!strcmp(a,"--mlock")) { lock_memory=true; continue; }
        if (!strcmp(a,"--minimal")) { minimal=true; continue; }
        if (!strcmp(a,"--version")) { puts("TDPS phase1 schema=2 fixed64 catch-up fixed-jobs"); return 0; }
        if (i+1==argc) { fprintf(stderr,"missing value: %s\n",a); return 2; }
        const char *v=argv[++i];
        if (!strcmp(a,"--mode")) mode=v;
        else if (!strcmp(a,"--out")) out=v;
        else if (!strcmp(a,"--sink")) sink=v;
        else if (!strcmp(a,"--period")) period=number(v);
        else if (!strcmp(a,"--deadline")) deadline=number(v);
        else if (!strcmp(a,"--jobs")) jobs=number(v);
        else if (!strcmp(a,"--iters")) iters=number(v);
        else if (!strcmp(a,"--queue")) qcap=number(v);
        else if (!strcmp(a,"--logger-cpu")) { uint64_t n=number(v); if(n>=CPU_SETSIZE) return 2; logger_cpu=(int)n; }
        else if (!strcmp(a,"--test-logger-delay-ns")) logger_delay_ns=number(v);
        else if (!strcmp(a,"--test-shock-job")) inject_job=number(v);
        else if (!strcmp(a,"--test-shock-ns")) inject_ns=number(v);
        else { fprintf(stderr,"unknown option: %s (stream is legacy, not an alias)\n",a); return 2; }
    }
    bool async=!strcmp(mode,"async"), deferred=!strcmp(mode,"deferred"), inl=!strcmp(mode,"inline");
    if ((!async&&!deferred&&!inl)||!out||!sink||!strcmp(out,sink)||!period||!deadline||!jobs||!iters||!qcap||
        jobs>10000000||qcap>10000000||deadline>INT64_MAX||period>INT64_MAX/jobs||
        (async&&logger_cpu<0)||(minimal&&!deferred)||inject_ns>10000000000ULL||logger_delay_ns>1000000000ULL) {
        fprintf(stderr,"invalid config; require --iters --out --sink; async needs --logger-cpu; minimal only deferred\n"); return 2;
    }
    samples=calloc((size_t)jobs,sizeof(*samples)); queue=calloc(qcap,sizeof(*queue));
    if (!samples||!queue) { perror("calloc"); return 1; }
    /* Touch every page and construct identical records BEFORE the timed interval. */
    memset(samples,0,(size_t)jobs*sizeof(*samples));
    for (size_t j=0;j<jobs;++j) {
        memset(samples[j].record,'T',64);
        for (unsigned b=0;b<8;++b) samples[j].record[b]=(unsigned char)((uint64_t)j>>(b*8));
    }
    for (size_t j=0;j<qcap;++j) queue[j]=SIZE_MAX;
    if (!atomic_is_lock_free(&head)||!atomic_is_lock_free(&tail)||!atomic_is_lock_free(&done)||!atomic_is_lock_free(&ready)) {
        fprintf(stderr,"requires lock-free atomics\n"); return 1;
    }
    /* Exclusive creation protects historical output. No fsync/durability promise. */
    sink_fd=open(sink,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0644);
    if(sink_fd<0) { perror("open sink"); return 1; }
    int out_fd=open(out,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0644);
    if(out_fd<0) { perror("open samples"); return 1; }
    FILE *csv=fdopen(out_fd,"w"); if(!csv) { perror("fdopen"); return 1; }
    pthread_t thread;
    if(async) {
        pthread_attr_t attr; pthread_attr_init(&attr);
        pthread_attr_setinheritsched(&attr,PTHREAD_EXPLICIT_SCHED);
        pthread_attr_setschedpolicy(&attr,SCHED_OTHER);
        struct sched_param sp={0}; pthread_attr_setschedparam(&attr,&sp);
        int rc=pthread_create(&thread,&attr,logger,NULL); pthread_attr_destroy(&attr);
        if(rc) { fprintf(stderr,"pthread_create: %s\n",strerror(rc)); return 1; }
        while(!atomic_load_explicit(&ready,memory_order_acquire)) sleep_until(now()+100000);
        if(logger_error) { fprintf(stderr,"logger setup: %s\n",strerror(logger_error)); return 1; }
    }
    if(lock_memory && mlockall(MCL_CURRENT|MCL_FUTURE)) { perror("mlockall"); return 1; }
    struct sched_param sp={0}; sched_getparam(0,&sp);
    fprintf(stderr,"schema=2 mode=%s jobs=%"PRIu64" period=%"PRIu64" deadline=%"PRIu64" iters=%"PRIu64" policy=%d priority=%d cpu=%d logger_cpu=%d queue=%zu record_bytes=64 minimal=%d mlock=%d test_shock_job=%"PRIu64" test_shock_ns=%"PRIu64" test_logger_delay_ns=%"PRIu64"\n",
        mode,jobs,period,deadline,iters,sched_getscheduler(0),sp.sched_priority,sched_getcpu(),logger_cpu,qcap,minimal,lock_memory,inject_job,inject_ns,logger_delay_ns);
    uint64_t epoch=now()+10000000, loop_end;
    size_t high_water=0;
    for(size_t j=0;j<jobs;++j) {
        struct sample *s=&samples[j]; s->release=epoch+(uint64_t)j*period;
        sleep_until(s->release); s->start=now(); payload(iters); s->compute_finish=now();
        if(!minimal) s->output_start=now();
        if(j==inject_job && inject_ns) sleep_until(now()+inject_ns);
        if(async) {
            size_t h=atomic_load_explicit(&head,memory_order_relaxed);
            size_t t=atomic_load_explicit(&tail,memory_order_acquire);
            if(h-t==qcap) s->dropped=1;
            else {
                queue[h%qcap]=j; s->accepted=1;
                atomic_store_explicit(&head,h+1,memory_order_release);
                if(h+1-t>high_water) high_water=h+1-t;
            }
        } else if(inl) { deliver(j); s->accepted=!s->delivery_errno; }
        else s->accepted=1; /* retained record, batch delivery after loop */
        if(!minimal) { s->output_finish=now(); s->cpu=sched_getcpu(); }
        else s->cpu=-1;
    }
    loop_end=now();
    if(async) { atomic_store_explicit(&done,true,memory_order_release); pthread_join(thread,NULL); }
    if(deferred) for(size_t j=0;j<jobs;++j) deliver(j);
    uint64_t drain_end=now();
    int failed=0; if(close(sink_fd)) { perror("close sink"); failed=1; }
    fprintf(csv,"schema_version,job,release_ns,start_ns,compute_finish_ns,finish_ns,wakeup_delay_ns,execution_ns,response_ns,lateness_ns,miss,cpu,output_start_ns,output_finish_ns,accepted,dropped,delivery_start_ns,delivery_finish_ns,delivery_errno\n");
    size_t accepted=0,dropped=0,errors=0;
    for(size_t j=0;j<jobs;++j) {
        struct sample *s=&samples[j];
        uint64_t response=s->compute_finish-s->release;
        int64_t late=(int64_t)response-(int64_t)deadline;
        fprintf(csv,"2,%zu,%"PRIu64",%"PRIu64",%"PRIu64",%"PRIu64",%"PRIu64",%"PRIu64",%"PRIu64",%"PRId64",%d,%d,%"PRIu64",%"PRIu64",%d,%d,%"PRIu64",%"PRIu64",%d\n",
            j,s->release,s->start,s->compute_finish,s->compute_finish,s->start-s->release,s->compute_finish-s->start,response,late,late>0,s->cpu,s->output_start,s->output_finish,s->accepted,s->dropped,s->delivery_start,s->delivery_finish,s->delivery_errno);
        accepted+=(size_t)s->accepted; dropped+=(size_t)s->dropped; errors+=(s->delivery_errno!=0);
    }
    if(ferror(csv)) failed=1;
    if(fclose(csv)) { perror("fclose samples"); failed=1; }
    fprintf(stderr,"loop_end_ns=%"PRIu64" drain_end_ns=%"PRIu64" accepted=%zu dropped=%zu delivery_errors=%zu queue_high_water=%zu\n",loop_end,drain_end,accepted,dropped,errors,high_water);
    free(queue); free(samples);
    return failed||errors ? 1 : 0;
}
