from fastapi import FastAPI


app = FastAPI(
    title="GitHub to Devin Webhook Service",
    description="Receives GitHub webhooks and starts Devin sessions.",
    version="0.1.0",
)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
