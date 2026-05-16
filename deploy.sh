#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Login to AWS ECR
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 716868103174.dkr.ecr.ap-south-1.amazonaws.com

# Variables
ECR_REPO_NAME="eons-hrm"
AWS_ACCOUNT_ID="716868103174"
REGION="ap-south-1"
TAG="latest"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO_NAME}"
LAMBDA_FUNCTION_NAME="eons-hrm"

# Step 1: Build Docker image
echo "Building Docker image..."
docker build --platform=linux/amd64 --provenance=false -t ${ECR_REPO_NAME}:${TAG} .

# Step 2: Tag the Docker image
echo "Tagging Docker image..."
docker tag ${ECR_REPO_NAME}:${TAG} ${ECR_URI}:${TAG}

# Step 3: Push the Docker image to Amazon ECR
echo "Pushing Docker image to Amazon ECR..."
docker push ${ECR_URI}:${TAG}

# Step 4: Update Lambda function code
echo "Updating Lambda function with new image..."
aws lambda update-function-code \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --image-uri ${ECR_URI}:${TAG} --no-cli-pager --output json || true

echo "Deployment completed successfully."
