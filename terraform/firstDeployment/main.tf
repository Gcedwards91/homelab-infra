resource "proxmox_vm_qemu" "debian_vm" {
  count = 1
  name        = "debian-test-${count.index +1}"
  target_node = "anorlondo"

  clone       = "debian-template"
  full_clone  = true
  scsihw = "virtio-scsi-single"

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

resource "proxmox_vm_qemu" "alma_vm" {
  count = 1
  name        = "alma-test-${count.index +1}"
  target_node = "anorlondo"

  clone       = "almalinux-template"
  full_clone  = true
  scsihw = "virtio-scsi-single"

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

  bios = "ovmf"
  machine = "q35"

  # Explicit cloud-init drive attachment
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

resource "proxmox_vm_qemu" "ubuntu_vm" {
  count = 1
  name        = "ubuntu-test-${count.index +1}"
  target_node = "anorlondo"

  clone       = "ubuntu-template"
  full_clone  = true
  scsihw = "virtio-scsi-single"
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