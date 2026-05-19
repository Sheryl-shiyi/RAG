#!/usr/bin/env python3
"""
Trigger Ingestion Pipeline - Create a new vector database.

This script sends a request to the Ingestion Pipeline service to ingest
documents from a URL, S3/MinIO bucket, or GitHub repository and build
a vector database backed by PGVector.

Prerequisites:
  Set up port-forward before running this script:
    oc port-forward -n llama-stack-rag svc/rag-ingestion-pipeline 8000:80

Usage:
  python scripts/trigger-pipeline.py --type url --name my-db \\
      --urls "https://arxiv.org/pdf/2408.09869"

  python scripts/trigger-pipeline.py --type s3 --name my-s3-db \\
      --bucket documents

  python scripts/trigger-pipeline.py --type github --name my-github-db \\
      --repo "https://github.com/rh-ai-quickstart/RAG.git" \\
      --path "notebooks/hr"
"""

import argparse
import json
import sys

import requests


# ---------------------------------------------------------------------------
# Payload builders — one per source type
# ---------------------------------------------------------------------------

def build_url_payload(args):
    """Build the request payload for URL-based ingestion."""
    urls = [u.strip() for u in args.urls.split(",")]
    return {
        "name": args.name,
        "version": args.version,
        "source": "URL",
        "embedding_model": args.embedding_model,
        "vector_store_name": _vector_store_name(args),
        "urls": urls,
    }


def build_s3_payload(args):
    """Build the request payload for S3/MinIO-based ingestion."""
    return {
        "name": args.name,
        "version": args.version,
        "source": "S3",
        "embedding_model": args.embedding_model,
        "vector_store_name": _vector_store_name(args),
        "access_key_id": args.access_key,
        "secret_access_key": args.secret_key,
        "endpoint_url": args.endpoint,
        "bucket_name": args.bucket,
        "region": args.region,
    }


def build_github_payload(args):
    """Build the request payload for GitHub-based ingestion."""
    return {
        "name": args.name,
        "version": args.version,
        "source": "GITHUB",
        "embedding_model": args.embedding_model,
        "vector_store_name": _vector_store_name(args),
        "url": args.repo,
        "path": args.path,
        "branch": args.branch,
        "token": args.token or "",
    }


def _vector_store_name(args):
    return f"{args.name}-v{args.version.replace('.', '-')}"


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------

PAYLOAD_BUILDERS = {
    "url": build_url_payload,
    "s3": build_s3_payload,
    "github": build_github_payload,
}

SENSITIVE_KEYS = {"secret_access_key", "token"}


def submit_pipeline(base_url: str, payload: dict) -> bool:
    """POST the payload to the ingestion service and report the result."""
    url = f"{base_url}/add"

    print(f"\n>>> Submitting request to {url}")

    display_payload = {
        k: ("***" if k in SENSITIVE_KEYS and v else v)
        for k, v in payload.items()
    }
    print(f"Payload:\n{json.dumps(display_payload, indent=2)}")

    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
    except requests.exceptions.ConnectionError:
        print(f"\nERROR: Cannot connect to {base_url}")
        print("Make sure port-forward is running:")
        print("  oc port-forward -n llama-stack-rag svc/rag-ingestion-pipeline 8000:80")
        return False

    if response.status_code == 200:
        result = response.json()
        print(f"\nPipeline created successfully!")
        print(f"Response:\n{json.dumps(result, indent=2)}")
        print(f"\nThe pipeline is running in the background. "
              f"Wait a few minutes, then verify with:")
        print(f"  oc get workflow -n llama-stack-rag")
        return True

    print(f"\nERROR: Request failed with status {response.status_code}")
    print(f"Details: {response.text}")
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Trigger the Ingestion Pipeline to create a new vector database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # Ingest from a URL (comma-separated for multiple)
  python trigger-pipeline.py --type url --name docling-db \\
      --urls "https://arxiv.org/pdf/2408.09869"

  # Ingest from an S3 / MinIO bucket
  python trigger-pipeline.py --type s3 --name minio-db --bucket documents

  # Ingest from a GitHub repository
  python trigger-pipeline.py --type github --name github-db \\
      --repo "https://github.com/rh-ai-quickstart/RAG.git" \\
      --path "notebooks/hr"
        """,
    )

    # -- Required --
    parser.add_argument(
        "--type", "-t", required=True, choices=["url", "s3", "github"],
        help="Data source type",
    )
    parser.add_argument(
        "--name", "-n", required=True,
        help="Name for the vector database",
    )

    # -- Common options --
    parser.add_argument(
        "--version", "-v", default="1.0",
        help="Database version (default: %(default)s)",
    )
    parser.add_argument(
        "--embedding-model", "-e",
        default="qwen-3-4b-embedding/qwen3-4b-embedding",
        help="Embedding model (default: %(default)s)",
    )
    parser.add_argument(
        "--base-url", "-u", default="http://localhost:8000",
        help="Ingestion Pipeline base URL (default: %(default)s)",
    )

    # -- URL source options --
    url_group = parser.add_argument_group("URL source options")
    url_group.add_argument("--urls", help="Comma-separated list of document URLs")

    # -- S3 source options --
    s3_group = parser.add_argument_group("S3 / MinIO source options")
    s3_group.add_argument("--bucket", help="S3/MinIO bucket name")
    s3_group.add_argument(
        "--endpoint", default="http://minio:9000",
        help="S3/MinIO endpoint (default: %(default)s)",
    )
    s3_group.add_argument(
        "--access-key", default="minio_rag_user",
        help="S3 access key (default: %(default)s)",
    )
    s3_group.add_argument(
        "--secret-key", default="minio_rag_password",
        help="S3 secret key (default: %(default)s)",
    )
    s3_group.add_argument(
        "--region", default="us-east-1",
        help="AWS region (default: %(default)s)",
    )

    # -- GitHub source options --
    gh_group = parser.add_argument_group("GitHub source options")
    gh_group.add_argument("--repo", help="GitHub repository URL")
    gh_group.add_argument("--path", help="Path within the repository to ingest")
    gh_group.add_argument(
        "--branch", default="main",
        help="Git branch (default: %(default)s)",
    )
    gh_group.add_argument("--token", help="GitHub token (for private repos)")

    args = parser.parse_args(argv)

    if args.type == "url" and not args.urls:
        parser.error("--urls is required when --type is 'url'")
    elif args.type == "s3" and not args.bucket:
        parser.error("--bucket is required when --type is 's3'")
    elif args.type == "github" and (not args.repo or not args.path):
        parser.error("--repo and --path are required when --type is 'github'")

    return args


def main():
    args = parse_args()
    payload = PAYLOAD_BUILDERS[args.type](args)
    success = submit_pipeline(args.base_url, payload)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
