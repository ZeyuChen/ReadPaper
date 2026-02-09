#!/bin/bash
set -e

# Configuration
REGION="us-central1"
PROJECT_ID=$(gcloud config get-value project)
REPO_NAME="readpaper-repo"
IMAGE_NAME="readpaper-texlive-base"
SOURCE_IMAGE="ghcr.io/xu-cheng/texlive-full:latest"
TARGET_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"

echo "Mirroring ${SOURCE_IMAGE} to ${TARGET_IMAGE}..."

# Pull from source
echo "Pulling ${SOURCE_IMAGE}..."
docker pull --platform linux/amd64 ${SOURCE_IMAGE}

# Tag for target
echo "Tagging..."
docker tag ${SOURCE_IMAGE} ${TARGET_IMAGE}

# Push to Artifact Registry
echo "Pushing to Artifact Registry..."
docker push ${TARGET_IMAGE}

echo "Done! You can now use ${TARGET_IMAGE} as your base image."
