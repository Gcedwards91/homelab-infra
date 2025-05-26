# Homelab Infrastructure 
This is a homelab project meant to be used to learn and deploy software leveraging DevOps pricinples. It will manifest in several phases. 

# Phase 1 - Initial Lab Setup
- Install Proxmox on Mini-PC: Completed
- Configure Mini-PC and Proxmox to use built in Wi-Fi 6 Card: Completed
- Install and configure base image snapshots of: Ubuntu, Debian, and AlmaLinux: Completed
- Configure future VMs to be reachable via SSH: Completed
- Configure future VMs to be reachable via browser, for consoles: Completed
- Configure control node (Terraform & Ansible) by hand: Completed
- Configure SIEM Node using Wazuh: Completed
- Configure monitoring node (Prometheus + Grafana): Completed
## Lessons Learned - Phase 1
- Proxmox VE is Debian-based but optimized for server use. As such it does not include WiFi drivers by default. To enable WiFi on the host, drivers were downloaded from a Debian-based WSL environment, transferred via USB, and installed using dpkg.
- When provisioning virtual machines (VMs) in Proxmox, using the Intel E1000 network adapter ensures compatibility out of the box. Unlike virtio, E1000 does not require special drivers, allowing new VMs tto immediately access package mirrors for updates and installations.
- In my environment the Proxmox host is a mini-pc that is assigned a static IP, while all VMs use DHCP. To make VMs reachable via hostname or IP from other devices and MobaXterm/VSCode, the following network design was used:
    - The WiFi NIC (wlp2s0) is configured as the primary network interface with a static IP for internet access.
    - A virtual bridge (vmbr0) is configured with no physical ports, using a static IP in the X.X.100.0/24 subnet, where X.X can be whichever octets you prefer. This serves as the internal network interface for all VMS.
    - dnsmasq was installed and configured to serve DHCP leases and internal DNS resoltution on vmbr0, allowing VMS to be accessed byu Fully Qualified Domain Names (FQDN).
    - A static route was added at my desktop to ensure any traffic to the X.X.100.0/24 subnet would be routed through the Proxmox host and to the VMs.
- To enable internal hostname resolution across the lab, and with my workstation, the desktop client was confgigured with the X.X.100.1 IP as part of its DNS, ensuring the homelab's domain lookups resolve through dnsmasq.
- Tools & Software used: Proxmox, Rufus, Wazuh, Prometheus, Node Exporter, Grafana, Terraform, Ansible, CMD, PowerShell, Bash.
# Phase 2 - Get Hands Dirty
- Deploy Virtual Machines using Terraform: In progress
- Configure Virtual Machines using Ansible: Not begun
- Write LAMP Stack Terrfaorm and Ansible Playbooks: Not begun
# Phase 3 - Containerize
- Deploy a master host for control node, SIEM node, and monitoring node: Not begun
- Containerize Terraform: Not begun
- Containerize Ansible: Not begun
- Containerize Wazuh: Not begun
- Containerize Prometheus: Not begun
- Containerize Grafana: Not begun
- Deploy VMs from Containerized master host: Not begun
- Write IaC .yml files to automate via Terraform & Ansible the deployment of the newly containerized master host: Not begun
# Phase 4 - Write & Host Resume
- Write HTML and CSS + JavaScript or Python to host a dynnamic Resume
- Write HTMl and CSS + JavaScript or Python to discuss the journey for this project