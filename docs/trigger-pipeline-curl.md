# 使用 curl 触发 Ingestion Pipeline

## 本地触发（需要 port-forward）

### 步骤 1: 开启 port-forward

```bash
oc port-forward -n llama-stack-rag svc/rag-ingestion-pipeline 8000:80
```

### 步骤 2: 调用 API

```bash
curl -X POST http://localhost:8000/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-minio-db",
    "version": "1.0",
    "source": "S3",
    "embedding_model": "qwen-3-4b-embedding/qwen3-4b-embedding",
    "vector_store_name": "my-minio-db-v1-0",
    "access_key_id": "minio_rag_user",
    "secret_access_key": "minio_rag_password",
    "endpoint_url": "http://minio:9000",
    "bucket_name": "documents",
    "region": "us-east-1"
  }'
```

---

## 远端触发（从集群内部，如 Jupyter Pod）

```bash
curl -X POST http://rag-ingestion-pipeline/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-minio-db",
    "version": "1.0",
    "source": "S3",
    "embedding_model": "qwen-3-4b-embedding/qwen3-4b-embedding",
    "vector_store_name": "my-minio-db-v1-0",
    "access_key_id": "minio_rag_user",
    "secret_access_key": "minio_rag_password",
    "endpoint_url": "http://minio:9000",
    "bucket_name": "documents",
    "region": "us-east-1"
  }'
```

---

## 单行版本（方便复制）

### 本地

```bash
curl -X POST http://localhost:8000/add -H "Content-Type: application/json" -d '{"name":"my-minio-db","version":"1.0","source":"S3","embedding_model":"qwen-3-4b-embedding/qwen3-4b-embedding","vector_store_name":"my-minio-db-v1-0","access_key_id":"minio_rag_user","secret_access_key":"minio_rag_password","endpoint_url":"http://minio:9000","bucket_name":"documents","region":"us-east-1"}'
```

### 远端

```bash
curl -X POST http://rag-ingestion-pipeline/add -H "Content-Type: application/json" -d '{"name":"my-minio-db","version":"1.0","source":"S3","embedding_model":"qwen-3-4b-embedding/qwen3-4b-embedding","vector_store_name":"my-minio-db-v1-0","access_key_id":"minio_rag_user","secret_access_key":"minio_rag_password","endpoint_url":"http://minio:9000","bucket_name":"documents","region":"us-east-1"}'
```

---

## 验证命令

```bash
# 查看 pipeline 状态
oc get workflow -n llama-stack-rag | tail -3

# 查看向量数据库
oc exec -n llama-stack-rag deploy/llamastack -- curl -s http://localhost:8321/v1/vector_stores
```

---

## API 参数说明

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `name` | 向量数据库名称 | `my-minio-db` |
| `version` | 版本号 | `1.0` |
| `source` | 数据源类型 | `S3`, `GITHUB`, `URL` |
| `embedding_model` | 嵌入模型 | `qwen-3-4b-embedding/qwen3-4b-embedding` |
| `vector_store_name` | 向量存储名称 | `my-minio-db-v1-0` |
| `access_key_id` | MinIO/S3 访问密钥 | `minio_rag_user` |
| `secret_access_key` | MinIO/S3 密钥 | `minio_rag_password` |
| `endpoint_url` | MinIO/S3 端点 | `http://minio:9000` |
| `bucket_name` | Bucket 名称 | `documents` |
| `region` | AWS 区域 | `us-east-1` |

---

## 可用的 Embedding 模型

| 模型 | 维度 |
|------|------|
| `qwen-3-4b-embedding/qwen3-4b-embedding` | 2560 |
| `sentence-transformers/nomic-ai/nomic-embed-text-v1.5` | 768 |
