from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import create_engine, text
import json
from typing import Dict, Any
from settings import db_config, well_permits_table

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def map_page():
    with open("map.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get("/api/permits")
async def get_permits() -> Dict[str, Any]:
    try:
        db_url = f"postgresql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
        engine = create_engine(db_url)

        query = f"""
        SELECT 
            "API" as api,
            "Perm_Appr" as permit_num,
            "Well_Name" as well_name,
            ST_AsGeoJSON(ST_Transform(geometry, 4326)) as geom,
            "Longitude" as lon,
            "Latitude" as lat
        FROM {well_permits_table} 
        WHERE geometry IS NOT NULL
        LIMIT 10000;
        """

        with engine.connect() as connection:
            result = connection.execute(text(query))
            rows = result.fetchall()

            features = []
            for row in rows:
                try:
                    # Use lon/lat if geometry fails
                    try:
                        geom = json.loads(row.geom)
                    except:
                        geom = {
                            "type": "Point",
                            "coordinates": [float(row.lon), float(row.lat)]
                        }

                    feature = {
                        "type": "Feature",
                        "geometry": geom,
                        "properties": {
                            "api": str(row.api) if row.api else "",
                            "permit_num": str(row.permit_num) if row.permit_num else "",
                            "well_name": str(row.well_name) if row.well_name else ""
                        }
                    }
                    features.append(feature)
                except Exception as e:
                    print(f"Error processing row: {e}")
                    continue

            geojson = {
                "type": "FeatureCollection",
                "features": features
            }

            return JSONResponse(content=geojson)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/refresh")
async def refresh_data():
    from scripts import download_and_load_to_postgis
    download_and_load_to_postgis()
    return {"message": "Data refresh completed"}