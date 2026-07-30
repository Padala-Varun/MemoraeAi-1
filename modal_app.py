"""
MemoraeAI — Modal Deployment Script

Deploys the FastAPI backend to Modal.com as a persistent web endpoint.
All secrets (API keys, DB URIs) are loaded from the 'memorae-secrets' Modal Secret.

Usage:
  modal serve modal_app.py   # dev (ephemeral URL)
  modal deploy modal_app.py  # production (permanent URL)
"""

import modal

# ── Modal Image: install all Python dependencies ──
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi==0.115.0",
        "uvicorn[standard]==0.30.0",
        "pydantic>=2.0,<3.0",
        "pydantic-settings>=2.0,<3.0",
        "pymongo[srv]==4.8.0",
        "motor==3.5.0",
        "qdrant-client==1.11.0",
        "neo4j==5.23.0",
        "langchain-core>=0.3.0,<0.4.0",
        "langchain-mistralai>=0.2.0,<0.3.0",
        "langgraph>=0.2.0,<0.3.0",
        "httpx>=0.27.0,<0.28.0",
        "python-dotenv>=1.0.0,<2.0.0",
        "composio>=0.18.0",
    )
    .add_local_dir("app", remote_path="/root/app", copy=True, ignore=["__pycache__"])
    .add_local_dir("web", remote_path="/root/web", copy=True)
)

# ── Modal App ──
app = modal.App(name="memorae-ai", image=image)


@app.function(
    secrets=[modal.Secret.from_name("memorae-secrets")],
    scaledown_window=300,
)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def web():
    """Serve the MemoraeAI FastAPI application."""
    import sys
    import os

    # Ensure /root is on the Python path so `app.*` imports resolve
    sys.path.insert(0, "/root")

    # Set working directory to /root so relative paths (e.g., web/ static mount) work
    os.chdir("/root")

    from app.main import create_app

    fastapi_app = create_app()
    return fastapi_app
