# ERA5 SWT circulation composites in ggplot (metR + sf). Reads era5_swt_composites.nc.
# Run: /opt/anaconda3/envs/rfigs/bin/Rscript maps.R
suppressMessages({library(ncdf4); library(tidyverse); library(metR); library(sf); library(rnaturalearth)})

base <- "/Users/smar0095/Fires_SWTs"
figs <- file.path(base, "R", "figs"); dir.create(figs, showWarnings = FALSE, recursive = TRUE)
ncf <- file.path(base, "era5_swt_composites.nc")
if (!file.exists(ncf)) ncf <- file.path(base, "era5_swt_composites_SYNTH.nc")
cat("reading", basename(ncf), "\n")

nc  <- nc_open(ncf)
swt <- ncvar_get(nc, "swt"); lon <- ncvar_get(nc, "lon"); lat <- ncvar_get(nc, "lat")
nd  <- ncvar_get(nc, "n_days")
# netcdf dims (swt,lat,lon) -> ncdf4 returns R array dims (lon,lat,swt)
t850 <- ncvar_get(nc, "t850_anom"); msl <- ncvar_get(nc, "msl_mean")
u850 <- ncvar_get(nc, "u850_anom"); v850 <- ncvar_get(nc, "v850_anom")
nc_close(nc)

HEAD <- c("FH-B", "WH-A", "TH-C", "WCT-B")
grid <- expand.grid(lon = lon, lat = lat)            # lon varies fastest (matches column-major slice)
mk <- function(s) {
  i <- which(swt == s)
  tibble(lon = grid$lon, lat = grid$lat,
         t850 = as.vector(t850[, , i]), msl = as.vector(msl[, , i]) / 100,
         u = as.vector(u850[, , i]), v = as.vector(v850[, , i]),
         swt = s, lab = sprintf("%s  (n=%d days)", s, nd[i]))
}
df <- bind_rows(lapply(HEAD, mk))
df$lab <- factor(df$lab, levels = unique(df$lab[order(match(df$swt, HEAD))]))

coast <- ne_countries(scale = "medium", returnclass = "sf")
vmax  <- max(abs(df$t850), na.rm = TRUE)

p <- ggplot(df, aes(lon, lat)) +
  geom_contour_fill(aes(z = t850), na.fill = TRUE,
                    breaks = seq(-ceiling(vmax), ceiling(vmax), length.out = 13)) +
  geom_contour(aes(z = msl), colour = "grey20", linewidth = 0.3,
               breaks = seq(980, 1040, 4)) +
  geom_arrow(aes(dx = u * 0.3, dy = v * 0.3), skip = 3, colour = "grey15",
             arrow.length = 0.3, min.mag = 0.5) +
  geom_sf(data = coast, fill = NA, colour = "black", linewidth = 0.35, inherit.aes = FALSE) +
  coord_sf(xlim = c(108, 165), ylim = c(-46, -8), expand = FALSE) +
  facet_wrap(~lab) +
  scale_fill_gradient2(low = "#2c6fbb", mid = "white", high = "#c0392b",
                       midpoint = 0, name = "T850\nanom (K)") +
  labs(x = NULL, y = NULL,
       title = "ERA5 circulation composites by SWT",
       subtitle = "Filled: 850 hPa temperature anomaly | contours: MSLP (hPa) | arrows: 850 hPa wind anomaly") +
  theme_bw(base_size = 11) +
  theme(panel.grid = element_line(colour = "grey92"))

ggsave(file.path(figs, "fig_circulation_composites.png"), p, width = 11, height = 8.5, dpi = 200)
cat("wrote fig_circulation_composites.png\n")
