resource "proxmox_vm_qemu" "debian_vm" {
  name        = "debian-test-01"
  target_node = "proxmox"

  clone       = "base-100"
  full_clone  = true

  cores       = 2
  memory      = 2048
  sockets     = 1

  network {
    model  = "e1000"
    bridge = "vmbr0"
  }

  disk {
    slot     = 0
    size     = "10G"
    type     = "scsi"
    storage  = "local-lvm"
    iothread = true
  }

  os_type = "cloud-init"

  ipconfig0 = "ip=dhcp"

  ssh_user     = "debian"
  ssh_private_key = file("~/.ssh/id_rsa")
}
