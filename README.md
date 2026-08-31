sudo sh -c '
for f in /sys/devices/system/cpu/cpu[0-9]*/cpufreq; do
    echo performance > "$f/scaling_governor"
    echo 3800000 > "$f/scaling_min_freq"
    echo 3800000 > "$f/scaling_max_freq"
done
'

Desative também o turbo/boost:

echo 0 | sudo tee /sys/devices/system/cpu/cpufreq/boost