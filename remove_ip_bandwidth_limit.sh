IFACE="ens8f0"

tc -s class show dev ens8f0
tc -s filter show dev ens8f0

# clean speed limit
# tc qdisc del dev ens8f0 root
echo "Run 'tc qdisc del dev ens8f0 root' to clean speed limit"