#!/bin/bash

# Log output to a timestamped log file
LOGFILE="template_config_$(date +%F_%H-%M-%S).log"
exec > >(tee -a "$LOGFILE") 2>&1

# Ensure the script is run as root
if [[ $EUID -ne 0 ]]; then
    echo ">>> This script must be run as root. Please use sudo." >&2
    exit 1
fi

# Confirm we are on a virtual machine
if ! systemd-detect-virt --vm &>/dev/null; then
    echo ">>> This does not appear to be a virtual machine. Exiting."
    exit 1
fi

echo "--- Beginning Template Configuration Process ---"

# Create iacadmin user
echo ">>> Creating iacadmin user..."
id iacadmin &>/dev/null || adduser iacadmin

# Add to sudo group
echo ">>> Adding iacadmin to sudo group..."
usermod -aG sudo iacadmin

# Set up SSH key
echo ">>> Setting up SSH key authentication for iacadmin..."
mkdir -p /home/iacadmin/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPyoZb0BO56lXd/4uh4rKHC145tpj3QJ52Om6qLzBNiC iacadmin@homelab" > /home/iacadmin/.ssh/authorized_keys
chmod 700 /home/iacadmin/.ssh
chmod 600 /home/iacadmin/.ssh/authorized_keys
chown -R iacadmin:iacadmin /home/iacadmin/.ssh

# Harden SSH
echo ">>> Hardening SSH config..."
sed -i 's/^#*PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#*ChallengeResponseAuthentication .*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh

# Set bash shell and prompt for iacadmin
echo ">>> Configuring shell and aliases for iacadmin..."
chsh -s /bin/bash iacadmin
cat <<EOF >> /home/iacadmin/.bashrc

# Custom Aliases
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
alias cls='clear'

# Colored prompt and timestamped history
force_color_prompt=yes
export HISTTIMEFORMAT="%F %T "
EOF
chown iacadmin:iacadmin /home/iacadmin/.bashrc

# Set timezone and locale
echo ">>> Setting timezone and locale..."
timedatectl set-timezone UTC
localectl set-locale LANG=en_US.UTF-8

# Detect OS and install packages
source /etc/os-release
echo ">>> Detected Distribution: $ID $VERSION_ID"

if [[ "$ID_LIKE" == *"rhel"* || "$ID" == "almalinux" ]]; then
    echo ">>> Using dnf..."
    dnf update -y
    dnf install -y qemu-guest-agent sudo vim curl wget net-tools openssh-server cloud-init
    systemctl enable --now qemu-guest-agent
elif [[ "$ID_LIKE" == *"debian"* || "$ID" == "debian" || "$ID" == "ubuntu" ]]; then
    echo ">>> Using apt..."
    apt update && apt full-upgrade -y
    apt install -y qemu-guest-agent sudo vim curl wget net-tools openssh-server cloud-init
    systemctl enable --now qemu-guest-agent
else
    echo ">>> Unrecognized distro. Exiting."
    exit 1
fi

# Enabling cloud-init
echo ">>> enabling cloud-init..."
systemctl enable cloud-init.service
systemctl enable cloud-init-local.service
systemctl enable cloud-config.service
systemctl enable cloud-final.service
cloud-init status

# Clean up cloud-init data
echo ">>> Cleaning cloud-init cache..."
cloud-init clean --logs

# Remove SSH host keys for regeneration on clone
# echo "Removing existing SSH host keys..."
# rm -f /etc/ssh/ssh_host_*

# Clean temp and logs
echo ">>> Cleaning temporary files and logs..."
apt clean || dnf clean all
rm -rf /tmp/*
find /var/log -type f -exec truncate -s 0 {} \;

# Fill disk with zeros to help thin provisioning
echo ">>> Zeroing free disk space (this may take time)..."
dd if=/dev/zero of=/zerofile bs=1M status=progress || true
rm -f /zerofile

# Final wipe of bash history and exit
history -c
echo "--- Template Configuration Complete ---"
