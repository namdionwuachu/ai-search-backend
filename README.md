AI Search Backend - CloudFormation & Lambda

🚀 An AWS-based AI-powered search backend using Lambda, OpenSearch, Amazon Bedrock, API Gateway, and S3.

📁 Project Structure
ai-search-backend/
│── cloudformation/
│   ├── ai_search_backend_cloudformation.yaml  # CloudFormation template
│── lambdas/
│   ├── ai_search/
│   │   ├── index.py  # AI Search Lambda function
│   │   ├── requirements.txt  # Dependencies
│   ├── document_ingestion/
│   │   ├── index.py  # Document ingestion Lambda function
│   │   ├── requirements.txt  # Dependencies
│── README.md  # Project documentation
│── .gitignore  # Ignore unnecessary files
🚀 Features

AI-powered document search using OpenSearch and Amazon Bedrock.
Document ingestion pipeline that processes PDFs, images, and text files.
Serverless architecture using AWS Lambda, S3, and API Gateway.
Automated deployment via CloudFormation.
📌 Prerequisites

Before deploying, ensure you have:

AWS CLI installed (Install AWS CLI)
IAM permissions to deploy CloudFormation stacks, Lambda, and API Gateway.
An S3 bucket for storing Lambda function ZIP files.
📦 Installation & Deployment

1️⃣ Clone the Repository
git clone https://github.com/your-username/ai-search-backend.git
cd ai-search-backend
2️⃣ Install Dependencies
Navigate to each Lambda function directory and install dependencies:

cd lambdas/document_ingestion
pip install -r requirements.txt -t .

cd ../ai_search
pip install -r requirements.txt -t .
3️⃣ Package & Upload Lambda Functions
Replace your-bucket-name with an existing S3 bucket.

cd lambdas/document_ingestion
zip -r document_ingestion.zip .
aws s3 cp document_ingestion.zip s3://your-bucket-name/

cd ../ai_search
zip -r ai_search.zip .
aws s3 cp ai_search.zip s3://your-bucket-name/
4️⃣ Deploy CloudFormation Stack
aws cloudformation deploy \
  --stack-name ai-search-backend \
  --template-file cloudformation/ai_search_backend_cloudformation.yaml \
  --capabilities CAPABILITY_NAMED_IAM
🛠 API Usage

Querying the AI Search API
Once deployed, your API Gateway endpoint will be available in CloudFormation Outputs.

Make a POST request to search for documents:

curl -X POST https://<api-gateway-endpoint>/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is our vacation policy?"}'
Expected Response
{
  "query": "What is our vacation policy?",
  "response": "The company's vacation policy allows...",
  "sources": [
    {
      "title": "Employee Handbook.pdf",
      "document_id": "s3://your-bucket/documents/handbook.pdf",
      "file_type": "pdf",
      "last_modified": "2024-03-09T12:00:00Z"
    }
  ]
}
📜 Troubleshooting

CloudFormation fails → Check if the S3 bucket exists and Lambda ZIP files are uploaded.
Lambda function errors → View logs in AWS CloudWatch.
CORS issues → Ensure API Gateway has the correct CORS headers.
📜 License

This project is licensed under the MIT License.
