"""Upload product JSON files to S3."""
import boto3
import os
from pathlib import Path
from typing import List

# Get configuration from environment variables
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_PREFIX = os.getenv("S3_PREFIX", "product-information/")
DATA_DIR = os.getenv("DATA_DIR", "data")
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")


def upload_product_files() -> List[str]:
    """Upload all product JSON files from data directory to S3."""
    if not S3_BUCKET_NAME:
        raise ValueError("S3_BUCKET_NAME environment variable not set")
    
    s3_client = boto3.client('s3', region_name=AWS_REGION)
    data_path = Path(DATA_DIR)
    
    if not data_path.exists():
        raise ValueError(f"Data directory does not exist: {DATA_DIR}")
    
    uploaded_files = []
    
    # Upload each JSON file to S3
    for json_file in sorted(data_path.glob("*.json")):
        s3_key = f"{S3_PREFIX}{json_file.name}"
        
        print(f"Uploading {json_file.name} to s3://{S3_BUCKET_NAME}/{s3_key}")
        
        # Read and upload the file
        with open(json_file, 'rb') as f:
            s3_client.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                Body=f,
                ContentType='application/json',
            )
        
        uploaded_files.append(s3_key)
        print(f"  ✓ Uploaded: {s3_key}")
    
    print(f"\n✓ Uploaded {len(uploaded_files)} files to s3://{S3_BUCKET_NAME}/{S3_PREFIX}")
    return uploaded_files


if __name__ == '__main__':
    try:
        upload_product_files()
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
