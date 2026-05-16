locals {
  startup_script = <<-EOT
    #!/bin/bash
    set -e

    # COS does not have gcloud — use the metadata server for auth instead.

    TOKEN=$(curl -sf "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
      -H "Metadata-Flavor: Google" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

    FINNHUB_API_KEY=$(curl -sf \
      "https://secretmanager.googleapis.com/v1/projects/${var.project_id}/secrets/${var.finnhub_secret_name}/versions/latest:access" \
      -H "Authorization: Bearer $TOKEN" | \
      python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['payload']['data']).decode())")

    export DOCKER_CONFIG=/tmp/docker-config
    mkdir -p $DOCKER_CONFIG
    echo "$TOKEN" | docker login -u oauth2accesstoken --password-stdin ${var.region}-docker.pkg.dev

    docker pull ${var.image}
    docker rm -f mag10-websocket 2>/dev/null || true

    docker run -d \
      --name mag10-websocket \
      --restart always \
      --log-driver=gcplogs \
      --log-opt gcp-project=${var.project_id} \
      -e FINNHUB_API_KEY="$FINNHUB_API_KEY" \
      -e GCP_PROJECT_ID="${var.project_id}" \
      -e PUBSUB_TOPIC_RAW_TRADES="${var.pubsub_topic_raw_trades}" \
      ${var.image}
  EOT
}

resource "google_compute_instance" "listener" {
  name         = "mag10-websocket-${var.env}"
  machine_type = "e2-micro"
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
      size  = 10
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }

  service_account {
    email  = var.service_account_email
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script         = local.startup_script
    google-logging-enabled = "true"
  }

  tags = ["mag10-websocket"]

  lifecycle {
    replace_triggered_by = [
      terraform_data.listener_image_trigger
    ]
  }
}

resource "terraform_data" "listener_image_trigger" {
  input = var.image
}
