resource "proxmox_vm_qemu" "debian_vm" {
  name        = "debian-test-01"
  target_node = "anorlondo"

  clone       = "highcommand"
  full_clone  = true

  cores       = 2
  memory      = 2048
  sockets     = 1

  network {
    id = 0
    model  = "e1000"
    bridge = "vmbr0"
  }

  disk {
    type      = "disk"
    interface = "scsi"
    slot      = "scsi0"
    size      = "16G"
    storage   = "local-lvm"
    format    = "qcow2"
  }

 # os_type = "cloud-init"

  ipconfig0 = "ip=dhcp"

  ssh_user     = "debian"
  ssh_private_key = file("/root/.ssh/id_ed25519")
}
