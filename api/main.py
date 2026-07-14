from fastapi import FastAPI


app = FastAPI(
    title="GitHub to Devin Automation Service",
    description="Runs scheduled and manually triggered GitHub-to-Devin workflows.",
    version="0.1.0",
)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
