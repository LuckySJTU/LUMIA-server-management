# LUMIA Server Management
This repo contains scripts of LUMIA server management, most of which are written by Python and Bash.
If you also use **slurm** as your hpc scheduler, you can use these scripts to help you manage your server.

We now have
- `backup_home.sh` A rsync backup script. The server backs up `/home` regularly with **crontab**.
- `gridview` A htop-like script monitoring job configs and node states of slurm. More controls on jobs will be added in the future.
- `lumia_slurm_rule` Auto-run every minute to apply lumia slurm preemption rule.
- `savai` A light script for users to show resources allocation on each node.

We hope these scripts help.

# Change log
## gridview
- 2025-2-19 udpate v1.6
    - add node state info
    - fix fractional memory bug
- 2025-2-14 update v1.5
    - improve flexibility
- 2025-1-6 update v1.4
    - flexible terminal size
    - cpu/mem/gpu state will be short when window is not wide enough
- 2024-12-11 update v1.3
    - fix some bug
- 2024-12-4 update v1.2
    - improve stability
- 2024-11-30 update v1.1 to github.
    - fix screen flashing when print a lot lines
    - decrease fresh time

## backup_home
- 2024-11-30 update to github.

## lumia_slurm_rule
- 2024-11-30 update to github.

## savai
- 2025-2-20 fix fractional memory bug
- 2025-1-19 add partition-queue info
- 2024-11-30 update to github.