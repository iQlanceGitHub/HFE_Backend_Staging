#!/usr/bin/env sh

echo "Creating SQS Queue"

AWS_REGION=foo
AWS_SQS_ENDPOINT=http://localhost:4566
AWS_SQS_QUEUE=scan-jobs

aws \
  --no-sign-request \
  --region $AWS_REGION \
  --endpoint-url=$AWS_SQS_ENDPOINT \
  sqs create-queue \
  --queue-name $AWS_SQS_QUEUE

echo "Created queue ok"