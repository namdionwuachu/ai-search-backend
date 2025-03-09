import boto3
import json
import os
import time
import tempfile
import subprocess
import urllib.parse
from opensearchpy import OpenSearch, RequestsHttpConnection
from datetime import datetime
from requests_aws4auth import AWS4Auth

def get_opensearch_client():
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

def extract_text_from_docx(s3_client, bucket, original_key, decoded_key=None):
    # If decoded_key is not provided, decode it
    if decoded_key is None:
        decoded_key = urllib.parse.unquote_plus(original_key)
        
    print(f"Extracting text from DOCX using pandoc: {decoded_key}")
    try:
        # Create a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            input_file = os.path.join(temp_dir, 'input.docx')
            
            # Use get_object instead of download_file
            response = s3_client.get_object(Bucket=bucket, Key=original_key)
            with open(input_file, 'wb') as f:
                f.write(response['Body'].read())
            
            # Use pandoc to convert DOCX to text
            result = subprocess.run(
                ['pandoc', input_file, '--from=docx', '--to=plain'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                print(f"Pandoc conversion failed: {result.stderr}")
                return None
                
    except Exception as e:
        print(f"Error extracting text from DOCX: {str(e)}")
        return None

def extract_text_from_file(bucket, key):
    # Store both the original and decoded keys
    original_key = key
    decoded_key = urllib.parse.unquote_plus(key)
    
    textract = boto3.client('textract')
    s3 = boto3.client('s3')
    
    try:
        print(f"Processing file: {decoded_key} from bucket: {bucket}")
        file_ext = decoded_key.split('.')[-1].lower()
        
        if file_ext in ['txt', 'json', 'md']:
            print(f"Processing text file with extension: {file_ext}")
            # Use original key for S3 operations
            response = s3.get_object(Bucket=bucket, Key=original_key)
            return response['Body'].read().decode('utf-8')
        
        elif file_ext in ['docx', 'doc']:
            # Try pandoc first - pass both original and decoded keys
            print("Attempting to process with pandoc")
            content = extract_text_from_docx(s3, bucket, original_key, decoded_key)
            if content:
                print("Successfully extracted text using pandoc")
                return content
            
            # Fall back to Textract if pandoc fails
            print("Pandoc failed, falling back to Textract")
            content = None
            
        if file_ext in ['pdf', 'png', 'jpg', 'jpeg'] or (file_ext in ['docx', 'doc'] and content is None):
            print(f"Processing document with Textract: {file_ext}")
            
            # Start async document analysis job - use original key
            response = textract.start_document_analysis(
                DocumentLocation={
                    'S3Object': {
                        'Bucket': bucket,
                        'Name': original_key
                    }
                },
                FeatureTypes=['TABLES', 'FORMS']
            )
            
            job_id = response['JobId']
            print(f"Started Textract job: {job_id}")
            
            # Wait for the job to complete
            while True:
                response = textract.get_document_analysis(JobId=job_id)
                status = response['JobStatus']
                print(f"Job status: {status}")
                
                if status in ['SUCCEEDED', 'FAILED']:
                    break
                time.sleep(3)
            
            if status == 'SUCCEEDED':
                text_content = []
                next_token = None
                
                # Get all pages
                while True:
                    if next_token:
                        response = textract.get_document_analysis(
                            JobId=job_id,
                            NextToken=next_token
                        )
                    else:
                        response = textract.get_document_analysis(JobId=job_id)
                    
                    # Extract text from all blocks
                    for block in response['Blocks']:
                        if block['BlockType'] == 'LINE':
                            text_content.append(block['Text'])
                    
                    # Check if there are more pages
                    if 'NextToken' in response:
                        next_token = response['NextToken']
                    else:
                        break
                
                return '\n'.join(text_content)
            else:
                error_message = response.get('StatusMessage', 'Unknown error')
                print(f"Textract job failed: {error_message}")
                return f"Error processing document: {error_message}"
        
        else:
            print(f"Unsupported file type: {file_ext}")
            return f"Unsupported file type: {file_ext}"
            
    except Exception as e:
        print(f"Error extracting text: {str(e)}")
        return str(e)

def lambda_handler(event, context):
    try:
        print("Processing S3 event:", json.dumps(event, indent=2))
        
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']  # Original key with encoding
            decoded_key = urllib.parse.unquote_plus(key)  # Decoded key for display
            
            print(f"Processing file {decoded_key} from bucket {bucket}")
            
            # Extract text content - pass the original key here
            content = extract_text_from_file(bucket, key)
            if not content:
                print(f"No content extracted from {decoded_key}, skipping")
                continue
            
            # Get file metadata
            s3 = boto3.client('s3')
            last_modified = datetime.utcnow().isoformat()  # Default
            
            try:
                # Try to get metadata but don't fail if we can't
                metadata = s3.head_object(Bucket=bucket, Key=key)
                last_modified = metadata['LastModified'].isoformat()
            except Exception as e:
                print(f"Warning: Could not get metadata: {str(e)}")
            
            # Prepare document for indexing
            document = {
                'content': content,
                'title': decoded_key.split('/')[-1],
                'document_id': key,  # Keep the original key as the document ID
                'file_type': decoded_key.split('.')[-1].lower(),
                'upload_date': datetime.utcnow().isoformat(),
                'last_modified': last_modified
            }
            
            print(f"Prepared document for indexing: {json.dumps(document, indent=2)}")
            
            # Initialize OpenSearch and index document - use original key for ID
            try:
                opensearch = get_opensearch_client()
                response = opensearch.index(
                    index='enterprise-docs',
                    body=document,
                    id=key,  # Use original key as ID
                    refresh=True
                )
                print(f"Successfully indexed document: {decoded_key}")
                print(f"OpenSearch response: {json.dumps(response, indent=2)}")
            except Exception as e:
                print(f"Error indexing document: {str(e)}")
                raise e
        
        return {
            'statusCode': 200,
            'body': json.dumps('Document processing complete')
        }
        
    except Exception as e:
        print(f"Error processing request: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error processing document: {str(e)}')
        }
