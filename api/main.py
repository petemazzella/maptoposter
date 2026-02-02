"""
FastAPI wrapper for maptoposter - generates beautiful map posters via API.
"""
import os
import subprocess
import base64
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="Map Poster API",
    description="Generate beautiful, minimalist map posters for any city",
    version="1.0.0"
)

# Available themes from maptoposter
THEMES = [
    "noir", "blueprint", "midnight_blue", "neon_cyberpunk", "japanese_ink",
    "terracotta", "sunset", "warm_beige", "pastel_dream", "ocean",
    "forest", "emerald", "copper_patina", "monochrome_blue",
    "gradient_roads", "contrast_zones", "autumn"
]

# Preset sizes (width x height in inches at 300 DPI)
SIZES = {
    "instagram": {"width": 3.6, "height": 3.6, "description": "1080x1080px"},
    "mobile": {"width": 3.6, "height": 6.4, "description": "1080x1920px"},
    "4k": {"width": 12.8, "height": 7.2, "description": "3840x2160px"},
    "a4": {"width": 8.27, "height": 11.69, "description": "2480x3508px"},
    "poster_small": {"width": 8, "height": 10, "description": "2400x3000px"},
    "poster_medium": {"width": 12, "height": 16, "description": "3600x4800px"},
    "poster_large": {"width": 18, "height": 24, "description": "5400x7200px"},
}

# Path to maptoposter script (in parent directory since we're in /api)
REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "create_map_poster.py"
POSTERS_DIR = REPO_ROOT / "posters"


class PosterRequest(BaseModel):
    """Request model for poster generation."""
    city: str = Field(..., description="City name", min_length=1)
    country: str = Field(..., description="Country name", min_length=1)
    theme: str = Field(default="noir", description="Poster theme")
    size: Optional[str] = Field(default=None, description="Preset size (instagram, mobile, 4k, a4, poster_small, poster_medium, poster_large)")
    width: Optional[float] = Field(default=None, description="Custom width in inches (max 20)", le=20, ge=1)
    height: Optional[float] = Field(default=None, description="Custom height in inches (max 20)", le=20, ge=1)
    distance: Optional[int] = Field(default=18000, description="Map radius in meters")
    display_city: Optional[str] = Field(default=None, description="Custom display name for city (e.g., for non-Latin scripts)")
    display_country: Optional[str] = Field(default=None, description="Custom display name for country")
    font_family: Optional[str] = Field(default=None, description="Google Font family name")


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Map Poster API",
        "version": "1.0.0",
        "endpoints": {
            "/generate": "POST - Generate a map poster",
            "/themes": "GET - List available themes",
            "/sizes": "GET - List preset sizes",
            "/health": "GET - Health check"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    script_exists = SCRIPT_PATH.exists()
    return {
        "status": "healthy" if script_exists else "degraded",
        "script_found": script_exists,
        "script_path": str(SCRIPT_PATH),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/themes")
async def list_themes():
    """List all available poster themes."""
    return {
        "themes": THEMES,
        "count": len(THEMES),
        "default": "noir"
    }


@app.get("/sizes")
async def list_sizes():
    """List all preset poster sizes."""
    return {
        "sizes": SIZES,
        "note": "You can also specify custom width/height in inches (max 20)"
    }


def run_poster_generation(request: PosterRequest, width: float, height: float) -> Path:
    """Run the maptoposter script and return the path to generated file."""

    # Ensure posters directory exists
    POSTERS_DIR.mkdir(exist_ok=True)

    # Build command
    cmd = [
        "uv", "run", str(SCRIPT_PATH),
        "--city", request.city,
        "--country", request.country,
        "--theme", request.theme,
        "--width", str(width),
        "--height", str(height),
        "--distance", str(request.distance),
    ]

    # Add optional parameters
    if request.display_city:
        cmd.extend(["--display-city", request.display_city])
    if request.display_country:
        cmd.extend(["--display-country", request.display_country])
    if request.font_family:
        cmd.extend(["--font-family", request.font_family])

    try:
        # Run maptoposter from repo root
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180  # 3 minute timeout for large posters
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Poster generation failed: {result.stderr}"
            )

        # Find the generated file
        if not POSTERS_DIR.exists():
            raise HTTPException(
                status_code=500,
                detail="Poster output directory not found"
            )

        # Get the most recent file matching our request
        poster_files = list(POSTERS_DIR.glob(f"*_{request.theme}_*.png"))

        if not poster_files:
            raise HTTPException(
                status_code=500,
                detail=f"Generated poster file not found. stdout: {result.stdout}"
            )

        # Get the most recently created file
        latest_file = max(poster_files, key=lambda f: f.stat().st_mtime)
        return latest_file

    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="Poster generation timed out"
        )


@app.post("/generate")
async def generate_poster(request: PosterRequest):
    """
    Generate a map poster for the specified city.
    Returns the generated PNG image file.
    """
    # Validate theme
    if request.theme not in THEMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid theme '{request.theme}'. Available themes: {', '.join(THEMES)}"
        )

    # Determine dimensions
    if request.size:
        if request.size not in SIZES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid size '{request.size}'. Available sizes: {', '.join(SIZES.keys())}"
            )
        width = SIZES[request.size]["width"]
        height = SIZES[request.size]["height"]
    elif request.width and request.height:
        width = request.width
        height = request.height
    else:
        # Default to poster_medium
        width = 12
        height = 16

    try:
        latest_file = run_poster_generation(request, width, height)

        # Generate unique filename for response
        unique_id = str(uuid.uuid4())[:8]
        response_filename = f"{request.city}_{request.country}_{request.theme}_{unique_id}.png"

        # Return the file
        return FileResponse(
            path=str(latest_file),
            media_type="image/png",
            filename=response_filename,
            headers={
                "X-Poster-City": request.city,
                "X-Poster-Country": request.country,
                "X-Poster-Theme": request.theme
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )


@app.post("/generate/base64")
async def generate_poster_base64(request: PosterRequest):
    """
    Generate a map poster and return as base64 string.
    Useful for n8n workflows that need to process the image data.
    """
    # Validate theme
    if request.theme not in THEMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid theme '{request.theme}'. Available themes: {', '.join(THEMES)}"
        )

    # Determine dimensions
    if request.size:
        if request.size not in SIZES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid size '{request.size}'. Available sizes: {', '.join(SIZES.keys())}"
            )
        width = SIZES[request.size]["width"]
        height = SIZES[request.size]["height"]
    elif request.width and request.height:
        width = request.width
        height = request.height
    else:
        width = 12
        height = 16

    try:
        latest_file = run_poster_generation(request, width, height)

        # Read and encode as base64
        with open(latest_file, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        unique_id = str(uuid.uuid4())[:8]
        filename = f"{request.city}_{request.country}_{request.theme}_{unique_id}.png"

        return JSONResponse({
            "success": True,
            "filename": filename,
            "city": request.city,
            "country": request.country,
            "theme": request.theme,
            "image_base64": image_data,
            "content_type": "image/png"
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
