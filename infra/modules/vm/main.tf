locals {
  startup_script = <<-EOT
    #!/bin/bash
    set -e

    # Fetch Finnhub API key from Secret Manager at boot time
    FINNHUB_API_KEY=$(gcloud secrets versions access latest \
      --secret=${var.finnhub_secret_name} \
      --project=${var.project_id})

    # Authenticate Docker to Artifact Registry
    gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

    # Pull the latest listener image
    docker pull ${var.listener_image}

    # Stop and remove any previous container
    docker rm -f mag10-listener 2>/dev/null || true

    # Run the listener
    docker run -d \
      --name mag10-listener \
      --restart always \
      --log-driver=gcplogs \
      --log-opt gcp-project=${var.project_id} \
      -e FINNHUB_API_KEY="$FINNHUB_API_KEY" \
      -e GCP_PROJECT_ID="${var.project_id}" \
      -e PUBSUB_TOPIC_VOLUME="${var.pubsub_topic_volume}" \
      -e PUBSUB_TOPIC_MOMENTUM="${var.pubsub_topic_momentum}" \
      -e PUBSUB_TOPIC_VOLATILITY="${var.pubsub_topic_volatility}" \
      -e PUBSUB_TOPIC_SECTOR="${var.pubsub_topic_sector}" \
      ${var.listener_image}
  EOT
}

resource "google_compute_instance" "listener" {
  name         = "mag10-listener-${var.env}"
  machine_type = "e2-micro"
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
      size  = 10 # GB — minimum for COS
    }
  }

  network_interface {
    network = "default"
    access_config {
      # Ephemeral external IP — required for outbound WebSocket to Finnhub
    }
  }

  service_account {
    email  = var.service_account_email
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script         = local.startup_script
    google-logging-enabled = "true"
  }

  tags = ["mag10-listener"]

  # Replace the VM when the image or startup script changes
  lifecycle {
    replace_triggered_by = [
      terraform_data.listener_image_trigger
    ]
  }
}

# Forces VM replacement when the listener image URI changes
resource "terraform_data" "listener_image_trigger" {
  input = var.listener_image
}
