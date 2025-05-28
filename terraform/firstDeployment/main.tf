resource "proxmox_vm_qemu" "debian_vm" {
  name        = "debian-test-01"
  target_node = "anorlondo"

  clone       = "debian-base-image"
  full_clone  = true

  cpu {
    cores   = 2
    sockets = 1
  }

  memory      = 2048

  network {
    id = 0
    model  = "e1000"
    bridge = "vmbr0"
  }

  disk {
    type      = "disk"
    #interface = "scsi"
    slot      = "scsi0"
    size      = "16G"
    storage   = "local-lvm"
    #format    = "qcow2"
  }

 # os_type = "cloud-init"

  ipconfig0 = "ip=dhcp"

  ssh_user     = "debian"
  ssh_private_key = file("/root/.ssh/id_ed25519")
}
