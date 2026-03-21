terraform {
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 3.0"
    }
  }
}

provider "openstack" {
  auth_url    = "http://localhost:${var.keystone_port}/v3"
  tenant_name = "admin"
  user_name   = "admin"
  password    = "password"
  region      = "RegionOne"
  insecure    = true
}

variable "keystone_port" {
  default = "35000"
}

variable "nova_port" {
  default = "38774"
}

# ── Data sources ──────────────────────────────────────────

data "openstack_images_image_v2" "cirros" {
  name        = "cirros-0.6.2"
  most_recent = true
}

data "openstack_compute_flavor_v2" "tiny" {
  name = "m1.tiny"
}

data "openstack_networking_network_v2" "public" {
  name = "public"
}

# ── Resources ─────────────────────────────────────────────

resource "openstack_compute_instance_v2" "test_vm" {
  name      = "tf-test-vm"
  image_id  = data.openstack_images_image_v2.cirros.id
  flavor_id = data.openstack_compute_flavor_v2.tiny.id

  network {
    uuid = data.openstack_networking_network_v2.public.id
  }
}

resource "openstack_blockstorage_volume_v3" "test_vol" {
  name = "tf-test-vol"
  size = 1
}

# ── Networking Resources ──────────────────────────────────

resource "openstack_networking_network_v2" "test_net" {
  name           = "tf-test-network"
  admin_state_up = true
}

resource "openstack_networking_subnet_v2" "test_subnet" {
  name       = "tf-test-subnet"
  network_id = openstack_networking_network_v2.test_net.id
  cidr       = "192.168.100.0/24"
  ip_version = 4
}

resource "openstack_networking_port_v2" "test_port" {
  name       = "tf-test-port"
  network_id = openstack_networking_network_v2.test_net.id

  fixed_ip {
    subnet_id = openstack_networking_subnet_v2.test_subnet.id
  }
}

# ── Outputs ───────────────────────────────────────────────

output "server_id" {
  value = openstack_compute_instance_v2.test_vm.id
}

output "server_status" {
  value = openstack_compute_instance_v2.test_vm.access_ip_v4
}

output "volume_id" {
  value = openstack_blockstorage_volume_v3.test_vol.id
}

output "network_id" {
  value = openstack_networking_network_v2.test_net.id
}

output "subnet_id" {
  value = openstack_networking_subnet_v2.test_subnet.id
}

output "port_id" {
  value = openstack_networking_port_v2.test_port.id
}
