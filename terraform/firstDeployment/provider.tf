terraform {
  required_providers {
    proxmox = {
      source  = "local/proxmox"
      version = ">= 2.9.14"
    }
  }
}

provider "proxmox" {
  pm_api_url = "https://10.0.0.2:8006/api2/json"
  pm_user    = "root@pam"
  pm_password = var.proxmox_password
  pm_tls_insecure = true
}
