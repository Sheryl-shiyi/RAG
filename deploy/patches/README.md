# RAG UI Patches

This directory contains patches for the RAG UI deployment to fix context window issues without modifying the upstream Docker image.

## Problem

The default RAG UI (`quay.io/rh-ai-quickstart/llamastack-dist-ui:0.2.33`) does not limit:
- Number of search results (can return too many documents)
- Output tokens (defaults to 4096)

This causes errors when using models with smaller context windows (e.g., `gemma-3-27b` with `--max-model-len=11000`):

```
'max_tokens' is too large: 4096.
This model's maximum context length is 11000 tokens
and your request has 6960 input tokens (4096 > 11000 - 6960)
```

## Solution

Override `direct.py` via ConfigMap to add:
- `MAX_NUM_RESULTS = 3` - Limits search results to reduce input tokens
- `MAX_TOKENS = 512` - Limits output tokens

## Files

| File | Description |
|------|-------------|
| `rag-ui-overrides-configmap.yaml` | ConfigMap containing the patched `direct.py` |
| `rag-deployment-patch.yaml` | Deployment patch to mount the ConfigMap |

## Usage

### Apply Patches

```bash
# 1. Apply the ConfigMap
oc apply -f rag-ui-overrides-configmap.yaml -n llama-stack-rag

# 2. Patch the deployment (using JSON patch)
oc patch deployment rag -n llama-stack-rag --type=json -p='[
  {
    "op": "add",
    "path": "/spec/template/spec/volumes/-",
    "value": {
      "name": "rag-ui-overrides",
      "configMap": {
        "name": "rag-ui-overrides"
      }
    }
  },
  {
    "op": "add",
    "path": "/spec/template/spec/containers/0/volumeMounts/-",
    "value": {
      "name": "rag-ui-overrides",
      "mountPath": "/app/llama_stack_ui/distribution/ui/page/playground/direct.py",
      "subPath": "direct.py"
    }
  }
]'

# 3. Wait for rollout
oc rollout status deployment/rag -n llama-stack-rag
```

### Rollback

```bash
# Remove the volume mount (adjust index if needed)
oc patch deployment rag -n llama-stack-rag --type=json -p='[
  {"op": "remove", "path": "/spec/template/spec/volumes/1"},
  {"op": "remove", "path": "/spec/template/spec/containers/0/volumeMounts/1"}
]'

# Delete the ConfigMap
oc delete configmap rag-ui-overrides -n llama-stack-rag
```

## Customization

Edit `rag-ui-overrides-configmap.yaml` and adjust:

```python
MAX_NUM_RESULTS = 3   # Increase for more context, decrease if hitting token limits
MAX_TOKENS = 512      # Increase for longer responses, decrease if hitting token limits
```

Then reapply:

```bash
oc apply -f rag-ui-overrides-configmap.yaml -n llama-stack-rag
oc rollout restart deployment/rag -n llama-stack-rag
```

## Token Budget Calculation

For a model with context window of `N` tokens:

```
Input Tokens + Max Tokens <= N

Where:
- Input Tokens ≈ System Prompt + (MAX_NUM_RESULTS × ~1500 tokens per document) + Query
- Max Tokens = MAX_TOKENS setting
```

Example for `gemma-3-27b` with `--max-model-len=11000`:
- MAX_NUM_RESULTS=3: ~4500 input tokens
- MAX_TOKENS=512: 512 output tokens
- Total: ~5000 < 11000 ✓
