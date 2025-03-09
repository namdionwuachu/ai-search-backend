import boto3
import json
import os
import time
from opensearchpy import OpenSearch, RequestsHttpConnection, OpenSearchException
from botocore.exceptions import ClientError
from requests_aws4auth import AWS4Auth

# AWS Clients
bedrock_client = boto3.client('bedrock-runtime')

# OpenSearch Configuration
def get_opensearch_client():
    """ Initializes and returns an OpenSearch client. """
    credentials = boto3.Session().get_credentials()
    region = os.environ.get('AWS_REGION', 'us-east-1')
    
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        region,
        'es',
        session_token=credentials.token
    )

    return OpenSearch(
        hosts=[{'host': os.environ['OPENSEARCH_DOMAIN'], 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )

# Search OpenSearch for relevant documents
def retrieve_docs(query, client, max_results=5):
    """ Retrieves relevant documents from OpenSearch using full-text search. """
    try:
        response = client.search(
            index="enterprise-docs",
            body={
                "query": {
                    "bool": {
                        "should": [
                            {"match": {"content": query}},
                            {"match": {"title": query}}
                        ]
                    }
                },
                "size": max_results
            }
        )
        return response["hits"]["hits"]
    
    except OpenSearchException as e:
        print(f"❌ OpenSearchException: {str(e)}")
        return []

# Generate AI response using Amazon Bedrock
def generate_response(query, retrieved_docs, max_retries=3):
    """ Uses Amazon Bedrock to generate an AI-powered response. """
    
    if not retrieved_docs:
        return "No relevant documents found."

    context = "\n".join([
        f"Document: {doc['_source'].get('title', 'Unknown')}\nContent: {doc['_source'].get('content', 'No content available')}"
        for doc in retrieved_docs
    ])

    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": f"Context:\n{context}\n\nQuery: {query}"}]
    }

    # Use the inference profile ARN instead of direct model ID
    model_id = os.environ.get('BEDROCK_MODEL_ID', 'arn:aws:bedrock:us-east-1:115322075248:inference-profile/us.anthropic.claude-3-5-sonnet-20241022-v2:0')

    for attempt in range(max_retries):
        try:
            response = bedrock_client.invoke_model(
                modelId=model_id, 
                body=json.dumps(payload)
            )
            
            response_body = json.loads(response.get('body').read())

            if 'content' in response_body and isinstance(response_body['content'], list):
                for content_item in response_body['content']:
                    if content_item.get('type') == 'text':
                        return content_item.get('text', '')

            return "Error: Unable to parse model response."
        
        except (ClientError, boto3.exceptions.Boto3Error) as e:
            print(f"⚠ Bedrock error (attempt {attempt + 1}): {str(e)}")
            if attempt == max_retries - 1:
                return "Error generating response from Bedrock."
            time.sleep(2 ** attempt)  # Exponential backoff

    return "Error: No valid response from Bedrock AI."

# Lambda Handler
def lambda_handler(event, context):
    """ AWS Lambda function entry point. """
    try:
        if not event.get("body"):
            return {"statusCode": 400, "body": json.dumps({"error": "Missing request body"})}

        body = json.loads(event["body"])
        query = body.get("query")

        if not query:
            return {"statusCode": 400, "body": json.dumps({"error": "Missing 'query' parameter"})}

        opensearch_client = get_opensearch_client()
        retrieved_docs = retrieve_docs(query, opensearch_client)
        ai_response = generate_response(query, retrieved_docs)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "query": query,
                "response": ai_response,
                "sources": retrieved_docs
            })
        }
    
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
