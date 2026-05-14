from fastapi import FastAPI, Request, Response
import httpx

app = FastAPI()
OLLAMA_URL = "http://localhost:11434"

@app.post("/api/generate")
async def proxy_generate(request: Request):
    body = await request.body()
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{OLLAMA_URL}/api/generate", data=body, headers=request.headers)
        return Response(content=response.content, status_code=response.status_code, headers=dict(response.headers))
