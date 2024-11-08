import requests
import zipfile
import geopandas as gpd
from io import BytesIO
from sqlalchemy import create_engine, text
from geoalchemy2 import Geometry
import fiona
import pandas as pd
from settings import db_config, well_permits_table

def download_and_load_to_postgis():
    url = "https://ecmc.state.co.us/documents/data/downloads/gis/PERMITS_SHP.ZIP"
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-US,en;q=0.9"
    }

    try:
        print("Downloading shapefile...")
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        zip_memory = BytesIO(response.content)

        print("Processing shapefile...")
        fiona.drvsupport.supported_drivers['ESRI Shapefile'] = 'ri'

        with zipfile.ZipFile(zip_memory) as zf:
            shp_file = next(f for f in zf.namelist() if f.endswith('.shp'))
            for filename in zf.namelist():
                if filename.startswith(shp_file[:-4]):
                    zf.extract(filename, '/tmp')

            gdf = gpd.read_file(f'/tmp/{shp_file}')

        db_url = f"postgresql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
        engine = create_engine(db_url)

        with engine.connect() as connection:
            exists = connection.execute(text(
                f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = '{well_permits_table}'
                )
                """
            )).scalar()

            if not exists:
                print(f"Creating new table: {well_permits_table}")
                gdf.to_postgis(
                    name=well_permits_table,
                    con=engine,
                    if_exists='replace',
                    index=False,
                    dtype={'geometry': Geometry(geometry_type='POINT', srid=26913)}
                )
            else:
                print("Checking for new records...")
                # Use uppercase "API" column name
                existing_apis = pd.read_sql(
                    f'SELECT "API" FROM {well_permits_table}',
                    engine
                )['API'].tolist()

                new_records = gdf[~gdf['API'].isin(existing_apis)]

                if not new_records.empty:
                    print(f"Adding {len(new_records)} new records...")
                    new_records.to_postgis(
                        name=well_permits_table,
                        con=engine,
                        if_exists='append',
                        index=False,
                        dtype={'geometry': Geometry(geometry_type='POINT', srid=26913)}
                    )
                else:
                    print("No new records to add")

        with engine.connect() as connection:
            result = connection.execute(text(f"SELECT COUNT(*) FROM {well_permits_table}"))
            count = result.fetchone()[0]
            print(f"Total records in table: {count}")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    download_and_load_to_postgis()