# Homelab Infrastructure Project (Started 5/20/2025)
This is a homelab project I spun up to get familiar with:
- Building an enterprise-like environment from scratch.
- Building familiarity with IaC tools like Terraform and Ansible.
- Building familiarity with containerization practices, Docker, and Kubernetes.
- Building familiarity with GitHub, git, and CI/CD. 
- Building familiarity with general DevOps and SRE best practices. 
## Phase 1 - Initial Lab Setup (Completed 5/25/2025)
- Install Proxmox on Mini-PC: <b>Completed</b>
- Configure Mini-PC and Proxmox to use built in Wi-Fi 6 Card: <b>Completed</b>
- Install and configure base image snapshots of: Ubuntu, Debian, and AlmaLinux: <b>Completed</b>
- Configure future VMs to be reachable via SSH: <b>Completed</b>
- Configure future VMs to be reachable via browser, for consoles: <b>Completed</b>
- Configure control node (Terraform & Ansible) by hand: <b>Completed</b>
- Configure SIEM Node using Wazuh: <b>Completed</b>
- Configure monitoring node (Prometheus + Grafana): <b>Completed</b>
### Lessons Learned - Phase 1 (5/20/2025 - 5/25/2025)
- Proxmox VE is Debian-based but optimized for server use. As such it does not include WiFi drivers by default. To enable WiFi on the host, drivers were downloaded from a Debian-based WSL environment, transferred via USB, and installed using dpkg.
- When provisioning virtual machines (VMs) in Proxmox, using the Intel E1000 network adapter ensures compatibility out of the box. Unlike virtio, E1000 does not require special drivers, allowing new VMs tto immediately access package mirrors for updates and installations.
- In my environment the Proxmox host is a mini-pc that is assigned a static IP, while all VMs use DHCP. To make VMs reachable via hostname or IP from other devices and MobaXterm/VSCode, the following network design was used:
    - The WiFi NIC (wlp2s0) is configured as the primary network interface with a static IP for internet access.
    - A virtual bridge (vmbr0) is configured with no physical ports, using a static IP in the X.X.100.0/24 subnet, where X.X can be whichever octets you prefer. This serves as the internal network interface for all VMS.
    - dnsmasq was installed and configured to serve DHCP leases and internal DNS resoltution on vmbr0, allowing VMS to be accessed byu Fully Qualified Domain Names (FQDN).
    - A static route was added at my desktop to ensure any traffic to the X.X.100.0/24 subnet would be routed through the Proxmox host and to the VMs.
- To enable internal hostname resolution across the lab, and with my workstation, the desktop client was confgigured with the X.X.100.1 IP as part of its DNS, ensuring the homelab's domain lookups resolve through dnsmasq.
- <b>Tools & Software used:</b> <i>Proxmox, Rufus, Wazuh, Prometheus, Node Exporter, Grafana, Terraform, Ansible, CMD, PowerShell, Bash.</i>
## Phase 2 - Get Hands Dirty (5/27/2025 - TBD)
- Deploy Virtual Machines using Terraform: <b>Completed</b>
- Automated VM Template Configuration via bash: <b>Completed</b>
- Automated boot order, cloud-init, and enabling qemu-guest-agent within Proxmox via bash: <b>Completed</b>
- Leverage cloud-init within Terraform to assign temporary hostnames for Ansible: <b>Completed</b>
- Deploy Varied Virtual Machines using Terraform: <b>Completed</b>
- Configure Virtual Machines using Ansible: <b>Not begun</b>
- Write LAMP Stack Terrfaorm and Ansible Playbooks: <b>Not begun</b>
## Phase 3 - Containerize
- Deploy a master host for control node, SIEM node, and monitoring node: <b>Not begun</b>
- Containerize Terraform: <b>Not begun</b>
- Containerize Ansible: <b>Not begun</b>
- Containerize Wazuh: <b>Not begun</b>
- Containerize Prometheus: <b>Not begun</b>
- Containerize Grafana: <b>Not begun</b>
- Deploy VMs from Containerized master host: <b>Not begun</b>
- Write IaC .yml files to automate via Terraform & Ansible the deployment of the newly containerized master host: <b>Not begun</b>
## Phase 4 - Build CI/CD Pipeline
- Research common CI/CD practices: <b>Not begun</b>
- Implement a CI/CD pipeline for Phase 5: <b>Not begun</b>
## Phase 5 - Write & Host Resume
- Write HTML and CSS + JavaScript or Python to host my dynamic Resume: <b>Not begun</b>
- Write HTML and CSS + JavaScript or Python to create a blog/project cover letter that discusses the journey for this project: <b>Not begun</b>
- Deploy 'Dynamic Resume' and 'Project Coverletter' to a LAMP Stack built in the spirit of the Cloud Resume Challenge: <b>Not begun</b>
- Implement CI/CD best practices in this phase: <b>Not begun</b>