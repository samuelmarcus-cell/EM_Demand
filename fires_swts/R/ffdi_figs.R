# FFDI fire-danger figures (uses only the VALID files: state CSV + composite nc mean field).
# Run: /opt/anaconda3/envs/rfigs/bin/Rscript ffdi_figs.R
suppressMessages({library(tidyverse); library(ncdf4); library(metR); library(sf); library(rnaturalearth)})
base <- "/Users/smar0095/Fires_SWTs"; figs <- file.path(base, "R", "figs")
dir.create(figs, showWarnings = FALSE, recursive = TRUE)
theme_set(theme_bw(base_size = 12))
HEAD <- c("FH-B", "WH-A", "TH-C", "WCT-B")

# ---- Fig A: per-SWT FFDI ANOMALY composite map (seasonally adjusted; the real deal) ----
nc  <- nc_open(file.path(base, "ffdi_swt_composite.nc"))
swt <- ncvar_get(nc, "swt"); lon <- ncvar_get(nc, "lon"); lat <- ncvar_get(nc, "lat")
nd  <- ncvar_get(nc, "n_days"); anom3 <- ncvar_get(nc, "ffdi_anom")   # ncdf4 -> (lon,lat,swt)
nc_close(nc)
grid <- expand.grid(lon = lon, lat = lat)
mapdf <- map_dfr(HEAD, function(s) {
  i <- which(swt == s)
  tibble(lon = grid$lon, lat = grid$lat, anom = as.vector(anom3[, , i]),
         panel = sprintf("%s  (n=%d days)", s, nd[i]))
})
vlim <- max(abs(mapdf$anom), na.rm = TRUE)
coast <- ne_countries(scale = "medium", returnclass = "sf")
pA <- ggplot(mapdf, aes(lon, lat)) +
  geom_raster(aes(fill = anom)) +
  geom_sf(data = coast, inherit.aes = FALSE, fill = NA, colour = "grey25", linewidth = 0.3) +
  coord_sf(xlim = c(112, 154), ylim = c(-44, -9), expand = FALSE) +
  scale_fill_gradient2(low = "#2166ac", mid = "white", high = "#b2182b", midpoint = 0,
                       limits = c(-vlim, vlim), name = "FFDI anomaly", na.value = "white") +
  facet_wrap(~panel) +
  labs(title = "FFDI anomaly by synoptic weather type (BARRA-R2, 1979-2023)",
       subtitle = "Seasonally adjusted (day-of-year climatology removed); red = elevated danger, blue = suppressed",
       x = NULL, y = NULL)
ggsave(file.path(figs, "fig_ffdi_anom_map.png"), pA, width = 10, height = 8, dpi = 150)
cat("wrote fig_ffdi_anom_map.png\n")

# ---- Fig B: state x SWT mean FFDI heatmap (which regimes are dangerous, where) ----
ff  <- read_csv(file.path(base, "ffdi_state_daily.csv"), show_col_types = FALSE) |>
  mutate(date = as.Date(date))
lab <- read_csv(file.path(base, "SWT_climatology_v20260129.csv"), show_col_types = FALSE) |>
  transmute(date = as.Date(time), assigned_SWT)
heat <- ff |> inner_join(lab, by = "date") |>
  filter(!is.na(ffdi), !is.na(assigned_SWT)) |>
  group_by(state, assigned_SWT) |>
  summarise(ffdi = mean(ffdi), .groups = "drop")
ord <- heat |> group_by(assigned_SWT) |> summarise(m = mean(ffdi)) |> arrange(m) |> pull(assigned_SWT)
heat <- heat |> mutate(assigned_SWT = factor(assigned_SWT, levels = ord),
                       state = factor(state, levels = c("TAS","VIC","NSW","QLD","SA","WA","NT")),
                       head = assigned_SWT %in% HEAD)
pB <- ggplot(heat, aes(assigned_SWT, state, fill = ffdi)) +
  geom_tile(colour = "white") +
  geom_tile(data = filter(heat, head), colour = "black", linewidth = 0.6, fill = NA) +
  scale_fill_viridis_c(option = "inferno", name = "mean FFDI") +
  labs(title = "Mean FFDI by state and synoptic weather type",
       subtitle = "SWTs ordered by overall danger; black outline = headline regimes",
       x = "Synoptic weather type (low -> high danger)", y = NULL) +
  theme(axis.text.x = element_text(angle = 90, vjust = 0.5, hjust = 1))
ggsave(file.path(figs, "fig_ffdi_state_swt_heat.png"), pB, width = 11, height = 4.5, dpi = 150)
cat("wrote fig_ffdi_state_swt_heat.png\n")
