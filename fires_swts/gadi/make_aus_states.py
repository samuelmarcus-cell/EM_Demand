"""Build a 7-state Australia polygon GeoJSON (ACT folded into NSW) for offline masking on Gadi."""
import geopandas as gpd, cartopy.io.shapereader as shpreader
shp = shpreader.natural_earth(resolution="50m", category="cultural", name="admin_1_states_provinces")
gdf = gpd.read_file(shp)
au = gdf[gdf["admin"] == "Australia"].copy()
namemap = {"New South Wales":"NSW","Victoria":"VIC","Queensland":"QLD","South Australia":"SA",
           "Western Australia":"WA","Tasmania":"TAS","Northern Territory":"NT",
           "Australian Capital Territory":"NSW"}   # ACT -> NSW
au["state"] = au["name"].map(namemap)
au = au.dropna(subset=["state"]).dissolve(by="state").reset_index()[["state", "geometry"]]
au.to_file("/Users/smar0095/Fires_SWTs/gadi/aus_states.geojson", driver="GeoJSON")
print("wrote aus_states.geojson with states:", sorted(au["state"]))
