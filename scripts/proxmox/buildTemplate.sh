#!/bin/bash

# Log output to a file with timestamp
LOGFILE="template_prep_$(date +%F_%H-%M-%S).log"
exec > >(tee -a "$LOGFILE") 2>&1

# Check if the script is being run as root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root. Please use sudo." >&2
    exit 1
fi

# Check for qm binary
if ! command -v qm &> /dev/null; then
    echo "Error: 'qm' command not found. Are you on a Proxmox host?"
    exit 1
fi

read -p "Enter a comma-separated list of VMIDs to configure (e.g., 700,800,900): " VMIDS
VMIDS=$(echo "$VMIDS" | tr -d '[:space:]')  # Trim whitespace

while true; do
    echo -e "\nThe following VMIDs will be prepped: $VMIDS"
    read -p "Is this correct? (y/n): " yesno
    case $yesno in
        [Yy]* )
            echo "Starting template prep for: $VMIDS"
            for i in ${VMIDS//,/ }; do
                if ! qm status "$i" &> /dev/null; then
                    echo "Warning: VMID $i does not exist. Skipping."
                    continue
                fi

                echo -e "\n>>> Preparing VMID $i..."

                sleep 1s

                if ! qm config "$i" | grep -q 'cloudinit'; then
                    echo ">>> Attaching Cloud Init Drive"
                    qm set "$i" --ide3 local-lvm:cloudinit
                else
                    echo ">>> Cloud Init Drive already exists. Skipping."
                fi

                sleep 1s

                echo ">>> Setting boot order"
                qm set "$i" --boot order=scsi0

                sleep 1s

                echo ">>> Enabling QEMU Agent"
                qm set "$i" --agent enabled=1

                sleep 1s

                echo -e "\n--- Final Config for VMID $i ---"
                qm config "$i" | grep -E 'cloudinit|boot|agent'
            done
            break
            ;;
        [Nn]* )
            echo "Operation cancelled."
            exit 1
            ;;
        * ) echo "Please answer yes or no." ;;
    esac
done
