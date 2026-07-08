# R/demand_composites.R
# Composite anomaly maps of high-demand days by dominant-hazard stratum.
# Run: /opt/anaconda3/envs/rfigs/bin/Rscript R/demand_composites.R
#
# ncdf4 reverses xarray dim order: xarray (stratum, lat, lon) -> ncdf4
# [lon, lat, stratum].

library(tidyverse)
library(ncdf4)
library(rnaturalearth)

nc_path <- "data/raw/composites/demand_composites.nc"
if (!file.exists(nc_path)) {
  stop("Missing ", nc_path,
       " - run the Gadi job (gadi/demand_composites.pbs) and copy the output here.")
}

nc      <- nc_open(nc_path)
lat     <- ncvar_get(nc, "lat")
lon     <- ncvar_get(nc, "lon")
strata  <- as.character(ncvar_get(nc, "stratum"))
n_days  <- ncvar_get(nc, "n_days")
get3d   <- function(v) ncvar_get(nc, v)  # [lon, lat, stratum]

panel_lab <- setNames(paste0(strata, " (n = ", n_days, ")"), strata)

grid <- expand_grid(stratum = factor(strata, levels = strata),
                    lat = lat, lon = lon)
# as.vector on [lon,lat,stratum] array is column-major: lon (first dim) varies fastest,
# then lat, then stratum. expand_grid's last argument (lon) varies fastest; thus orders match.

frame_of <- function(prefix) {
  grid |>
    mutate(anom = as.vector(get3d(paste0(prefix, "_anom"))),
           mean = as.vector(get3d(paste0(prefix, "_mean"))),
           p    = as.vector(get3d(paste0(prefix, "_p"))),
           panel = factor(panel_lab[as.character(stratum)],
                          levels = panel_lab))
}

aus <- ne_countries(country = "Australia", scale = "medium", returnclass = "sf")

caption_txt <- paste(
  "Stippling: pointwise p < 0.05 (composite t-test). Descriptive only:",
  "no field-wise multiplicity correction, and serial dependence within",
  "events makes it anti-conservative.")

# Stipple layer: every 3rd grid point with p < 0.05
stipple <- function(df) {
  df |>
    filter(p < 0.05,
           lon %in% lon[seq(1, length(lon), 3)],
           lat %in% lat[seq(1, length(lat), 3)])
}

base_theme <- theme_minimal(base_size = 9) +
  theme(panel.grid = element_blank(),
        plot.caption = element_text(size = 6.5, hjust = 0))

dir.create("R/figs", showWarnings = FALSE, recursive = TRUE)

# -- MSL: anomaly fill (hPa) + mean contours ---------------------------------
msl <- frame_of("msl") |> mutate(anom = anom / 100, mean = mean / 100)
p1 <- ggplot(msl) +
  geom_raster(aes(lon, lat, fill = anom)) +
  geom_contour(aes(lon, lat, z = mean), colour = "grey25",
               linewidth = 0.2, bins = 12) +
  geom_point(data = stipple(msl), aes(lon, lat), size = 0.05,
             colour = "black", alpha = 0.5) +
  geom_sf(data = aus, fill = NA, colour = "grey40", linewidth = 0.2,
          inherit.aes = FALSE) +
  scale_fill_distiller(palette = "RdBu", name = "MSLP anom (hPa)",
                       limits = c(-1, 1) * max(abs(msl$anom), na.rm = TRUE)) +
  coord_sf(xlim = range(lon), ylim = range(lat), expand = FALSE) +
  facet_wrap(~panel) +
  labs(title = "MSLP composite anomalies, high-demand days by dominant hazard",
       x = NULL, y = NULL, caption = caption_txt) +
  base_theme
ggsave("R/figs/fig_composite_msl.png", p1, width = 10, height = 6, dpi = 300)
cat("wrote R/figs/fig_composite_msl.png\n")

# -- T850 anomaly fill + 850 hPa wind anomaly vectors ------------------------
t850 <- frame_of("t850")
u    <- as.vector(get3d("u850_anom"))
v    <- as.vector(get3d("v850_anom"))
t850$u <- u; t850$v <- v
vec <- t850 |>
  filter(lon %in% lon[seq(1, length(lon), 4)],
         lat %in% lat[seq(1, length(lat), 4)])
sc <- 1.5  # degrees per (m/s) vector scaling
p2 <- ggplot(t850) +
  geom_raster(aes(lon, lat, fill = anom)) +
  geom_point(data = stipple(t850), aes(lon, lat), size = 0.05,
             colour = "black", alpha = 0.5) +
  geom_segment(data = vec,
               aes(lon, lat, xend = lon + sc * u, yend = lat + sc * v),
               arrow = arrow(length = unit(0.03, "cm")),
               linewidth = 0.15, colour = "grey15") +
  geom_sf(data = aus, fill = NA, colour = "grey40", linewidth = 0.2,
          inherit.aes = FALSE) +
  scale_fill_distiller(palette = "RdBu", name = "T850 anom (K)",
                       limits = c(-1, 1) * max(abs(t850$anom), na.rm = TRUE)) +
  coord_sf(xlim = range(lon), ylim = range(lat), expand = FALSE) +
  facet_wrap(~panel) +
  labs(title = "850 hPa temperature + wind anomalies, high-demand days by dominant hazard",
       x = NULL, y = NULL, caption = caption_txt) +
  base_theme
ggsave("R/figs/fig_composite_t850_wind.png", p2, width = 10, height = 6, dpi = 300)
cat("wrote R/figs/fig_composite_t850_wind.png\n")

# -- TCWV anomaly fill --------------------------------------------------------
tcwv <- frame_of("tcwv")
p3 <- ggplot(tcwv) +
  geom_raster(aes(lon, lat, fill = anom)) +
  geom_point(data = stipple(tcwv), aes(lon, lat), size = 0.05,
             colour = "black", alpha = 0.5) +
  geom_sf(data = aus, fill = NA, colour = "grey40", linewidth = 0.2,
          inherit.aes = FALSE) +
  scale_fill_distiller(palette = "BrBG", direction = 1,
                       name = "TCWV anom (kg m⁻²)",
                       limits = c(-1, 1) * max(abs(tcwv$anom), na.rm = TRUE)) +
  coord_sf(xlim = range(lon), ylim = range(lat), expand = FALSE) +
  facet_wrap(~panel) +
  labs(title = "Total column water vapour anomalies, high-demand days by dominant hazard",
       x = NULL, y = NULL, caption = caption_txt) +
  base_theme
ggsave("R/figs/fig_composite_tcwv.png", p3, width = 10, height = 6, dpi = 300)
cat("wrote R/figs/fig_composite_tcwv.png\n")

nc_close(nc)
