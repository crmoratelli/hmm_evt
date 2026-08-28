# Episódios de degradação: interference/interf_io

Um estado é degradado quando a taxa de miss estimada é pelo menos 50%. Um run é severo quando pelo menos 1% das ativações pertencem a estados degradados.

| environment | run | severity | degraded_occupancy | degraded_episodes | median_episode_us | p95_episode_us | max_episode_us | worst_state_miss_rate | worst_state_mean_response_ns |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| container | docker_cpu3-interf_io-run3 | degradação moderada | 0.0005 | 6.0 | 25000.0 | 92500.0 | 100000.0 | 1.0 | 36177328.3261 |
| container | docker_cpu3-interf_io-run10 | degradação severa | 0.0522 | 67.0 | 115000.0 | 1988500.0 | 2145000.0 | 0.9925 | 667185427.6681 |
| container | docker_cpu3-interf_io-run4 | degradação severa | 0.0234 | 57.0 | 150000.0 | 536000.0 | 1420000.0 | 1.0 | 651955723.3936 |
| container | docker_cpu3-interf_io-run5 | degradação severa | 0.0211 | 97.0 | 90000.0 | 439000.0 | 1070000.0 | 1.0 | 334708880.8598 |
| container | docker_cpu3-interf_io-run6 | degradação severa | 0.0248 | 127.0 | 50000.0 | 239500.0 | 2245000.0 | 1.0 | 1414139479.2111 |
| container | docker_cpu3-interf_io-run7 | degradação severa | 0.0513 | 86.0 | 127500.0 | 1506250.0 | 2810000.0 | 1.0 | 1304408612.9676 |
| container | docker_cpu3-interf_io-run8 | degradação severa | 0.05 | 71.0 | 120000.0 | 1855000.0 | 2550000.0 | 1.0 | 1455608434.5034 |
| container | docker_cpu3-interf_io-run9 | degradação severa | 0.0363 | 61.0 | 155000.0 | 1470000.0 | 1955000.0 | 1.0 | 1078935917.6912 |
| container | docker_cpu3-interf_io-run1 | sem degradação material | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |  |  |
| container | docker_cpu3-interf_io-run2 | sem degradação material | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |  |  |
| host | host_cpu3-interf_io-run2 | degradação moderada | 0.0007 | 1.0 | 335000.0 | 335000.0 | 335000.0 | 1.0 | 161215694.6418 |
| host | host_cpu3-interf_io-run3 | degradação moderada | 0.0021 | 25.0 | 35000.0 | 94000.0 | 190000.0 | 1.0 | 83679178.3514 |
| host | host_cpu3-interf_io-run4 | degradação moderada | 0.0055 | 48.0 | 50000.0 | 129500.0 | 200000.0 | 1.0 | 98915378.2985 |
| host | host_cpu3-interf_io-run10 | degradação severa | 0.0308 | 77.0 | 90000.0 | 798000.0 | 2725000.0 | 1.0 | 1053355742.9364 |
| host | host_cpu3-interf_io-run5 | degradação severa | 0.0116 | 79.0 | 10000.0 | 212500.0 | 845000.0 | 1.0 | 408563721.5011 |
| host | host_cpu3-interf_io-run6 | degradação severa | 0.0304 | 71.0 | 95000.0 | 865000.0 | 2120000.0 | 1.0 | 1295845080.8032 |
| host | host_cpu3-interf_io-run7 | degradação severa | 0.0402 | 79.0 | 125000.0 | 1280500.0 | 2465000.0 | 1.0 | 1223065693.9979 |
| host | host_cpu3-interf_io-run8 | degradação severa | 0.0401 | 75.0 | 105000.0 | 982500.0 | 2615000.0 | 1.0 | 1134199757.3508 |
| host | host_cpu3-interf_io-run9 | degradação severa | 0.0238 | 67.0 | 105000.0 | 360000.0 | 1975000.0 | 1.0 | 971720670.5648 |
| host | host_cpu3-interf_io-run1 | sem degradação material | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |  |  |

## Agregado por ambiente

| environment | severity | runs | median_degraded_occupancy | median_episodes | median_max_episode_us |
| --- | --- | --- | --- | --- | --- |
| container | degradação moderada | 1 | 0.0005 | 6.0 | 100000.0 |
| container | degradação severa | 7 | 0.0363 | 71.0 | 2145000.0 |
| container | sem degradação material | 2 | 0.0 | 0.0 | 0.0 |
| host | degradação moderada | 3 | 0.0021 | 25.0 | 200000.0 |
| host | degradação severa | 6 | 0.0306 | 76.0 | 2292500.0 |
| host | sem degradação material | 1 | 0.0 | 0.0 | 0.0 |
