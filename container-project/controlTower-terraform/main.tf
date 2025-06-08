resource "proxmox_vm_qemu" "control_tower" {
  count = 1
  name        = "control-tower"
  target_node = "anorlondo"

  clone       = "ubuntu-template"
  full_clone  = true
  scsihw = "virtio-scsi-single"
  cpu {
    cores   = 6
    sockets = 1
  }

  memory      = 8192

  network {
    id = 0
    model  = "e1000"
    bridge = "vmbr0"
  }

  disk {
    type      = "disk"
    #interface = "scsi"
    slot      = "scsi0"
    size      = "100G"
    storage   = "local-lvm"
    #format    = "qcow2"
  }

  #bootdisk = "scsi0"
 #  boot = "order=scsi0"
  # Cloud-init disk
  disk {
    type      = "cloudinit"
    slot      = "ide2"
    storage   = "local-lvm"
    size      = "4G"
  }
  os_type = "cloud-init"

  ipconfig0 = "ip=dhcp"

  ssh_user     = "iacadmin"
  ssh_private_key = file("/root/.ssh/id_ed25519")
}