from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import rasterio as rio
from rasterio.transform import from_gcps
from rasterio.control import GroundControlPoint
import os

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

IMAGE_DIR = "./images"
os.makedirs(IMAGE_DIR, exist_ok=True)
app.mount("/frontend", StaticFiles(directory=IMAGE_DIR), name="frontend")

click_data = {
    "click_count": 0,
    "x_values": [],
    "y_values": [],
    "lon_values": [],
    "lat_values": [],
    "uploaded_image": None
}

@app.post("/upload-image/")
async def upload_image(file: UploadFile):
    data = await file.read()
    file_location = os.path.join(IMAGE_DIR, file.filename).replace("\\", "/")
    with open(file_location, "wb") as f:
        f.write(data)
   
    click_data["uploaded_image"] = file_location
    click_data["click_count"] = 0
    click_data["x_values"].clear()
    click_data["y_values"].clear()
    click_data["lon_values"].clear()
    click_data["lat_values"].clear()
   
    return {"info": "file uploaded successfully", "file_location": file_location}

OUTPUT_IMAGE = os.path.join(IMAGE_DIR, 'georeferenced_image.tif')

@app.post("/add-gcp/")
async def add_gcp(x: float = Form(...), y: float = Form(...), lon: float = Form(...), lat: float = Form(...)):
    click_data["x_values"].append(x)
    click_data["y_values"].append(y)
    click_data["lon_values"].append(lon)
    click_data["lat_values"].append(lat)
    click_data["click_count"] += 1
   
    return {"info": f"GCP {click_data['click_count']} added", "x": x, "y": y, "lon": lon, "lat": lat}

@app.post("/georeference/")
async def georeference():
    min_gcp_count = 3  # Minimum number of GCPs required
    if len(click_data["x_values"]) < min_gcp_count:
        raise HTTPException(status_code=400, detail=f"At least {min_gcp_count} GCPs are required")
    
    x_values = click_data["x_values"]
    y_values = click_data["y_values"]
    lon_values = click_data["lon_values"]
    lat_values = click_data["lat_values"]
    
    gcps = [GroundControlPoint(col=x_values[i], row=y_values[i], x=lon_values[i], y=lat_values[i]) for i in range(len(x_values))]
    
    transform = from_gcps(gcps)
    crs = 'epsg:4326'
    output_filepath = OUTPUT_IMAGE

    if click_data["uploaded_image"] is None:
        raise HTTPException(status_code=400, detail="No image uploaded")
    
    try:
        with rio.open(click_data["uploaded_image"], 'r+') as ds:
            with rio.open(output_filepath, 'w', driver='GTiff',
                          height=ds.height, width=ds.width,
                          count=ds.count, dtype=ds.dtypes[0],
                          crs=crs, transform=transform) as dst:
                for i in range(1, ds.count + 1):
                    dst.write(ds.read(i), i)
        
        return {"info": "Image georeferenced successfully", "output_file": output_filepath}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to georeference image: {str(e)}")

@app.get("/download-georeferenced-image/")
async def download_georeferenced_image():
    if not os.path.exists(OUTPUT_IMAGE):
        raise HTTPException(status_code=404, detail="Georeferenced image not found")
   
    return FileResponse(OUTPUT_IMAGE, media_type='image/tiff', filename='georeferenced_image.tif')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
