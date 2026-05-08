output "instance_name" {
  value = google_compute_instance.listener.name
}

output "instance_self_link" {
  value = google_compute_instance.listener.self_link
}

output "external_ip" {
  value = google_compute_instance.listener.network_interface[0].access_config[0].nat_ip
}
