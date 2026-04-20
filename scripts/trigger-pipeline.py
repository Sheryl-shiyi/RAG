#!/usr/bin/env python3
"""
Trigger Ingestion Pipeline - 创建新向量数据库

用法:
  1. 先设置 port-forward:
     oc port-forward -n llama-stack-rag svc/rag-ingestion-pipeline 8000:80
  
  2. 运行脚本:
     python scripts/trigger-pipeline.py --type url --name my-db --urls "https://arxiv.org/pdf/2408.09869"
     python scripts/trigger-pipeline.py --type s3 --name my-s3-db --bucket documents
     python scripts/trigger-pipeline.py --type github --name my-github-db --repo "https://github.com/rh-ai-quickstart/RAG.git" --path "notebooks/hr"
"""

import argparse
import json
import requests
import sys


def create_from_url(args):
    """从 URL 创建向量数据库"""
    urls = [u.strip() for u in args.urls.split(",")]
    vector_store_name = f"{args.name}-v{args.version.replace('.', '-')}"
    
    payload = {
        "name": args.name,
        "version": args.version,
        "source": "URL",
        "embedding_model": args.embedding_model,
        "vector_store_name": vector_store_name,
        "urls": urls
    }
    return payload


def create_from_s3(args):
    """从 S3/MinIO 创建向量数据库"""
    vector_store_name = f"{args.name}-v{args.version.replace('.', '-')}"
    
    payload = {
        "name": args.name,
        "version": args.version,
        "source": "S3",
        "embedding_model": args.embedding_model,
        "vector_store_name": vector_store_name,
        "access_key_id": args.access_key,
        "secret_access_key": args.secret_key,
        "endpoint_url": args.endpoint,
        "bucket_name": args.bucket,
        "region": args.region
    }
    return payload


def create_from_github(args):
    """从 GitHub 创建向量数据库"""
    vector_store_name = f"{args.name}-v{args.version.replace('.', '-')}"
    
    payload = {
        "name": args.name,
        "version": args.version,
        "source": "GITHUB",
        "embedding_model": args.embedding_model,
        "vector_store_name": vector_store_name,
        "url": args.repo,
        "path": args.path,
        "branch": args.branch,
        "token": args.token or ""
    }
    return payload


def submit_pipeline(base_url: str, payload: dict):
    """提交 pipeline 请求"""
    url = f"{base_url}/add"
    
    print(f"\n📤 提交请求到 {url}")
    
    display_payload = payload.copy()
    if "secret_access_key" in display_payload:
        display_payload["secret_access_key"] = "***"
    if display_payload.get("token"):
        display_payload["token"] = "***"
    print(f"📝 Payload:\n{json.dumps(display_payload, indent=2)}")
    
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n✅ Pipeline 创建成功!")
            print(f"📊 响应:\n{json.dumps(result, indent=2)}")
            print(f"\n⏳ Pipeline 正在后台运行，请等待几分钟后验证结果")
            print(f"   验证命令: oc get workflow -n llama-stack-rag")
            return True
        else:
            print(f"\n❌ 请求失败: {response.status_code}")
            print(f"错误信息: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"\n❌ 无法连接到 {base_url}")
        print("请确保已运行 port-forward:")
        print("  oc port-forward -n llama-stack-rag svc/rag-ingestion-pipeline 8000:80")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="触发 Ingestion Pipeline 创建新向量数据库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从 URL 创建
  python trigger-pipeline.py --type url --name docling-db --urls "https://arxiv.org/pdf/2408.09869"
  
  # 从 MinIO 创建
  python trigger-pipeline.py --type s3 --name minio-db --bucket documents
  
  # 从 GitHub 创建
  python trigger-pipeline.py --type github --name github-db \\
    --repo "https://github.com/rh-ai-quickstart/RAG.git" --path "notebooks/hr"
        """
    )
    
    parser.add_argument("--type", "-t", required=True, choices=["url", "s3", "github"],
                        help="数据源类型: url, s3, github")
    parser.add_argument("--name", "-n", required=True,
                        help="向量数据库名称")
    parser.add_argument("--version", "-v", default="1.0",
                        help="版本号 (默认: 1.0)")
    parser.add_argument("--embedding-model", "-e", default="qwen-3-4b-embedding/qwen3-4b-embedding",
                        help="嵌入模型 (默认: qwen-3-4b-embedding, 可选: sentence-transformers/nomic-ai/nomic-embed-text-v1.5)")
    parser.add_argument("--base-url", "-u", default="http://localhost:8000",
                        help="Ingestion Pipeline URL (默认: http://localhost:8000)")
    
    # URL 参数
    parser.add_argument("--urls", help="PDF URL 列表 (逗号分隔)")
    
    # S3 参数
    parser.add_argument("--bucket", help="S3/MinIO bucket 名称")
    parser.add_argument("--endpoint", default="http://minio:9000",
                        help="S3/MinIO endpoint (默认: http://minio:9000)")
    parser.add_argument("--access-key", default="minio_rag_user",
                        help="S3 access key (默认: minio_rag_user)")
    parser.add_argument("--secret-key", default="minio_rag_password",
                        help="S3 secret key (默认: minio_rag_password)")
    parser.add_argument("--region", default="us-east-1",
                        help="AWS region (默认: us-east-1)")
    
    # GitHub 参数
    parser.add_argument("--repo", help="GitHub 仓库 URL")
    parser.add_argument("--path", help="仓库内的文档路径")
    parser.add_argument("--branch", default="main",
                        help="Git 分支 (默认: main)")
    parser.add_argument("--token", help="GitHub token (可选，用于私有仓库)")
    
    args = parser.parse_args()
    
    # 验证参数
    if args.type == "url" and not args.urls:
        parser.error("--type url 需要 --urls 参数")
    elif args.type == "s3" and not args.bucket:
        parser.error("--type s3 需要 --bucket 参数")
    elif args.type == "github" and (not args.repo or not args.path):
        parser.error("--type github 需要 --repo 和 --path 参数")
    
    # 构建 payload
    if args.type == "url":
        payload = create_from_url(args)
    elif args.type == "s3":
        payload = create_from_s3(args)
    else:
        payload = create_from_github(args)
    
    # 提交请求
    success = submit_pipeline(args.base_url, payload)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
