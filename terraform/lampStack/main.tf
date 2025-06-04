resource "proxmox_vm_qemu" "alma_web_01" {
  count = 1
  name        = "alma-web-01"
  target_node = "anorlondo"

  clone       = "debian-template"
  full_clone  = true
  scsihw = "virtio-scsi-single"
  hostname        = "alma-web-01"

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
    size      = "32G"
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


resource "proxmox_vm_qemu" "alma_web_02" {
  count = 1
  name        = "alma-web-02"
  target_node = "anorlondo"

  clone       = "debian-template"
  full_clone  = true
  scsihw = "virtio-scsi-single"
  hostname        = "alma-web-02"

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
    size      = "32G"
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

resource "proxmox_vm_qemu" "alma_db_01" {
  count = 1
  name        = "alma-db-01"
  target_node = "anorlondo"

  clone       = "debian-template"
  full_clone  = true
  scsihw = "virtio-scsi-single"
  hostname        = "alma-db-01"

  cpu {
    cores   = 4
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
    size      = "32G"
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
