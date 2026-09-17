# AWS Setup Guide

## Prerequisites

1. AWS account with free tier access
2. AWS CLI installed and configured
3. Docker installed locally

## Setup Steps

### 1. Configure AWS CLI

```bash
aws configure
# Enter your Access Key ID
# Enter your Secret Access Key
# Enter your default region (e.g., us-east-1)
# Enter your output format (json)
```

### 2. Create IAM Role

Create an IAM role with the following policies:
- AmazonS3FullAccess
- AmazonSQSFullAccess
- CloudWatchLogsFullAccess
- AmazonEC2ContainerRegistryFullAccess

### 3. Setup ECR (Elastic Container Registry)

```bash
# Create repository
aws ecr create-repository --repository-name gps-inference

# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com

# Tag and push image
docker tag gps-inference:latest YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/gps-inference:latest
docker push YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/gps-inference:latest
```

### 4. Deploy to EC2

Option A: Manual deployment

```bash
# Launch EC2 instance
aws ec2 run-instances \
  --image-id ami-0c7217cdde317cfec \
  --instance-type t2.micro \
  --key-name your-key-pair \
  --security-groups gps-inference-sg

# SSH into instance
ssh -i your-key.pem ubuntu@INSTANCE_IP

# Install Docker and run container
sudo apt update
sudo apt install -y docker.io
sudo docker run -d -p 8000:8000 gps-inference:latest
```

Option B: CI/CD deployment

The GitHub Actions workflow `.github/workflows/deploy-ec2.yml` handles this automatically.

### 5. Setup API Gateway (Optional)

For public API access:

```bash
# Create REST API
aws apigateway create-rest-api --name "GPS Inference API"

# Configure routes
# ... (use AWS Console or aws-cli commands)
```

### 6. Setup SQS for Async Processing

```bash
# Create queue
aws sqs create-queue --queue-name gps-inference-jobs

# Get queue URL
aws sqs get-queue-url --queue-name gps-inference-jobs
```

### 7. Setup CloudWatch Monitoring

```bash
# Create log group
aws logs create-log-group --log-group-name /aws/gps-inference

# Create metric filters
aws logs put-metric-filter \
  --log-group-name /aws/gps-inference \
  --filter-name Errors \
  --filter-pattern "ERROR" \
  --metric-transformations \
    metricName=ErrorCount,metricNamespace=GPSInference,metricValue=1
```

## Cost Estimation (Free Tier)

| Service | Free Tier Limit | Expected Usage |
|---------|----------------|----------------|
| EC2 | 750 hours/month t2.micro | ~720 hours |
| Lambda | 1M requests/month | ~100K requests |
| SQS | 1M requests/month | ~50K messages |
| API Gateway | 1M API calls/month | ~100K calls |
| CloudWatch | 10 metrics, 5GB logs | ~3 metrics |

Total estimated cost: **$0/month** within free tier limits

## Production Considerations

1. Use Application Load Balancer (ALB) for load balancing
2. Enable HTTPS with ACM certificate
3. Use CloudFront for CDN
4. Implement rate limiting in API Gateway
5. Setup auto-scaling for EC2
6. Use RDS for persistent storage
7. Setup backup and disaster recovery
