#!/bin/bash

# Log function to prepend timestamp to each log message
log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Navigate to the directory where your Git repository is located
# Uncomment the line below and replace with your directory path if needed
# cd /path/to/your/repository

log "Starting the git pull operation."

# Execute git pull origin master
# git pull origin master

# Check if the pull was successful
if [ $? -eq 0 ]; then
  log "Git pull successful!"
else
  log "Git pull failed! Exiting script."
  exit 1
fi

# make create_migration
# make migrate
# make migrate_on_docker
# Define the image name
IMAGE_NAME="hfe_backend-fast-api"
log "Image name is set to '$IMAGE_NAME'."

# Get the container ID(s) associated with the image
CONTAINER_IDS=$(docker ps -a --filter "ancestor=$IMAGE_NAME" --format "{{.ID}}")

# Check if any container IDs were found
if [ -z "$CONTAINER_IDS" ]; then
  log "No containers found for image '$IMAGE_NAME'."
else
  log "Container ID(s) for image '$IMAGE_NAME': $CONTAINER_IDS"
fi

# Stop and remove the containers
for CONTAINER_ID in $CONTAINER_IDS; do
  log "Stopping container $CONTAINER_ID..."
  docker stop "$CONTAINER_ID"

  if [ $? -eq 0 ]; then
    log "Successfully stopped container $CONTAINER_ID."
  else
    log "Failed to stop container $CONTAINER_ID."
  fi

  log "Removing container $CONTAINER_ID..."
  docker rm "$CONTAINER_ID"

  if [ $? -eq 0 ]; then
    log "Successfully removed container $CONTAINER_ID."
  else
    log "Failed to remove container $CONTAINER_ID."
  fi
done

log "All containers for image '$IMAGE_NAME' have been stopped and removed."

# Get the image ID using docker images, grep, and awk
IMAGE_ID=$(docker images --format "{{.ID}}" --filter "reference=$IMAGE_NAME")

# Check if the image ID was found
if [ -z "$IMAGE_ID" ]; then
  log "Image '$IMAGE_NAME' not found."
else
  log "Image ID for '$IMAGE_NAME': $IMAGE_ID"
fi

# Remove the Docker image
log "Removing the image '$IMAGE_NAME'..."
docker rmi $IMAGE_NAME

if [ $? -eq 0 ]; then
  log "Successfully removed image '$IMAGE_NAME'."
else
  log "Failed to remove image '$IMAGE_NAME'."
fi

# Bring up the containers using Docker Compose
log "Starting Docker Compose..."
docker compose up -d

if [ $? -eq 0 ]; then
  log "Docker Compose started successfully."
else
  log "Failed to start Docker Compose."
  exit 1
fi

docker exec -it $(docker ps --filter "ancestor=$IMAGE_NAME" --format "{{.ID}}" | head -n 1) make create_migration
if [ $? -ne 0 ]; then
  log "Error: Failed to execute 'make create_migration'. Exiting script."
  exit 1
fi

docker exec -it $(docker ps --filter "ancestor=$IMAGE_NAME" --format "{{.ID}}" | head -n 1) make migrate
if [ $? -ne 0 ]; then
  log "Error: Failed to execute 'make migrate'. Exiting script."
  exit 1
fi

log "Script completed successfully."
