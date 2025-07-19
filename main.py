from fastapi import FastAPI

app = FastAPI(
    title="AIC News Agency API",
    description="A basic API for the AIC News Agency.",
    version="0.0.1"
)

@app.get("/")
def read_root():
    """Root endpoint."""
    return {"message": "AIC News Agency API is running."}

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "AIC News Agency API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)