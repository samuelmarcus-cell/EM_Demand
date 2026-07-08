# R/demand_composites.R
# Composite anomaly maps of high-demand days by dominant-hazard stratum.
# Run: /opt/anaconda3/envs/rfigs/bin/Rscript R/demand_composites.R
#
# Main figures show HAZARD strata only (fire, tc, and flood once the AGCD
# adoption gate closes). drfa-led is a funding activation, not a hazard —
# it is plotted in separate supplementary figures (fig_supp_drfa_*) so the
# main panels never present it as a third hazard pathway.
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

hazard_strata <- setdiff(strata, "drfa-led")

aus <- ne_countries(country = "Australia", scale = "medium", returnclass = "sf")

caption_txt <- paste(
  "Stippling: pointwise p < 0.05 (composite t-test). Descriptive only:",
  "no field-wise multiplicity correction, and serial dependence within",
  "events makes it anti-conservative.")

drfa_caption <- str_wrap(paste(
  "DRFA is a disaster-funding activation, not a hazard: it mixes hazards and",
  "lags the causal meteorology by days to weeks. Shown for completeness,",
  "excluded from the fingerprint comparison.", caption_txt), width = 95)

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

# Anomaly colour limits are computed over ALL strata so main and
# supplementary figures for the same field share one scale and stay
# visually comparable.

# -- MSL: anomaly fill (hPa) + mean contours ---------------------------------
msl <- frame_of("msl") |> mutate(anom = anom / 100, mean = mean / 100)
msl_lim <- c(-1, 1) * max(abs(msl$anom), na.rm = TRUE)
plot_msl <- function(df, title, caption, file, width) {
  p <- ggplot(df) +
    geom_raster(aes(lon, lat, fill = anom)) +
    geom_contour(aes(lon, lat, z = mean), colour = "grey25",
                 linewidth = 0.2, bins = 12) +
    geom_point(data = stipple(df), aes(lon, lat), size = 0.05,
               colour = "black", alpha = 0.5) +
    geom_sf(data = aus, fill = NA, colour = "grey40", linewidth = 0.2,
            inherit.aes = FALSE) +
    scale_fill_distiller(palette = "RdBu", name = "MSLP anom (hPa)",
                         limits = msl_lim) +
    coord_sf(xlim = range(lon), ylim = range(lat), expand = FALSE) +
    facet_wrap(~panel) +
    labs(title = title, x = NULL, y = NULL, caption = caption) +
    base_theme
  ggsave(file, p, width = width, height = 6, dpi = 300)
  cat("wrote", file, "\n")
}
plot_msl(filter(msl, stratum %in% hazard_strata),
         "MSLP composite anomalies, high-demand days by dominant hazard",
         caption_txt, "R/figs/fig_composite_msl.png", 10)
plot_msl(filter(msl, stratum == "drfa-led"),
         "MSLP composite anomalies, DRFA-led high-demand days (non-hazard diagnostic)",
         drfa_caption, "R/figs/fig_supp_drfa_msl.png", 6)

# -- T850 anomaly fill + 850 hPa wind anomaly vectors ------------------------
t850 <- frame_of("t850")
t850$u <- as.vector(get3d("u850_anom"))
t850$v <- as.vector(get3d("v850_anom"))
t850_lim <- c(-1, 1) * max(abs(t850$anom), na.rm = TRUE)
sc <- 1.5  # degrees per (m/s) vector scaling
plot_t850 <- function(df, title, caption, file, width) {
  vec <- df |>
    filter(lon %in% lon[seq(1, length(lon), 4)],
           lat %in% lat[seq(1, length(lat), 4)])
  p <- ggplot(df) +
    geom_raster(aes(lon, lat, fill = anom)) +
    geom_point(data = stipple(df), aes(lon, lat), size = 0.05,
               colour = "black", alpha = 0.5) +
    geom_segment(data = vec,
                 aes(lon, lat, xend = lon + sc * u, yend = lat + sc * v),
                 arrow = arrow(length = unit(0.03, "cm")),
                 linewidth = 0.15, colour = "grey15") +
    geom_sf(data = aus, fill = NA, colour = "grey40", linewidth = 0.2,
            inherit.aes = FALSE) +
    scale_fill_distiller(palette = "RdBu", name = "T850 anom (K)",
                         limits = t850_lim) +
    coord_sf(xlim = range(lon), ylim = range(lat), expand = FALSE) +
    facet_wrap(~panel) +
    labs(title = title, x = NULL, y = NULL, caption = caption) +
    base_theme
  ggsave(file, p, width = width, height = 6, dpi = 300)
  cat("wrote", file, "\n")
}
plot_t850(filter(t850, stratum %in% hazard_strata),
          "850 hPa temperature + wind anomalies, high-demand days by dominant hazard",
          caption_txt, "R/figs/fig_composite_t850_wind.png", 10)
plot_t850(filter(t850, stratum == "drfa-led"),
          "850 hPa temperature + wind anomalies, DRFA-led days (non-hazard diagnostic)",
          drfa_caption, "R/figs/fig_supp_drfa_t850_wind.png", 6)

# -- TCWV anomaly fill --------------------------------------------------------
tcwv <- frame_of("tcwv")
tcwv_lim <- c(-1, 1) * max(abs(tcwv$anom), na.rm = TRUE)
plot_tcwv <- function(df, title, caption, file, width) {
  p <- ggplot(df) +
    geom_raster(aes(lon, lat, fill = anom)) +
    geom_point(data = stipple(df), aes(lon, lat), size = 0.05,
               colour = "black", alpha = 0.5) +
    geom_sf(data = aus, fill = NA, colour = "grey40", linewidth = 0.2,
            inherit.aes = FALSE) +
    scale_fill_distiller(palette = "BrBG", direction = 1,
                         name = "TCWV anom (kg m⁻²)",
                         limits = tcwv_lim) +
    coord_sf(xlim = range(lon), ylim = range(lat), expand = FALSE) +
    facet_wrap(~panel) +
    labs(title = title, x = NULL, y = NULL, caption = caption) +
    base_theme
  ggsave(file, p, width = width, height = 6, dpi = 300)
  cat("wrote", file, "\n")
}
plot_tcwv(filter(tcwv, stratum %in% hazard_strata),
          "Total column water vapour anomalies, high-demand days by dominant hazard",
          caption_txt, "R/figs/fig_composite_tcwv.png", 10)
plot_tcwv(filter(tcwv, stratum == "drfa-led"),
          "Total column water vapour anomalies, DRFA-led days (non-hazard diagnostic)",
          drfa_caption, "R/figs/fig_supp_drfa_tcwv.png", 6)

nc_close(nc)
