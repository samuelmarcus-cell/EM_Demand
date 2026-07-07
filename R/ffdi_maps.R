# FFDI danger-footprint maps for fire benchmark demand days.
# Run: /opt/anaconda3/envs/rfigs/bin/Rscript R/ffdi_maps.R
#
# NC dim order (xarray export): date × lat × lon → ncdf4 reverses to lon × lat × date.
# VERIFIED via Python: ffdi dims are (date=146, lat=691, lon=886) in xarray,
# so ncdf4 reads as [lon × lat × date] i.e. ffdi[lon_idx, lat_idx, date_idx].

library(tidyverse)
library(ncdf4)
library(sf)
library(rnaturalearth)

# ── 1. Open NetCDF ──────────────────────────────────────────────────────────
nc  <- nc_open("data/raw/ffdi/ffdi_maps.nc")

lat  <- ncvar_get(nc, "lat")   # length 691, ascending: -44.5 .. -10.0
lon  <- ncvar_get(nc, "lon")   # length 886, 112.0 .. 156.25
date_raw <- ncvar_get(nc, "date")  # days since 1950-01-10 (float)

# Convert dates: epoch is 1950-01-10
epoch <- as.Date("1950-01-10")
dates <- epoch + floor(date_raw)   # use floor: raw values are .5 fractional days; floor gives the correct calendar date
cat("Date range:", format(dates[1]), "to", format(dates[length(dates)]), "\n")
# Expect: 1979-12-29 .. 2023-12-13

# ncdf4 reverses xarray dim order: xarray (date, lat, lon) → ncdf4 [lon, lat, date]
ffdi_arr <- ncvar_get(nc, "ffdi")   # dim: [886, 691, 146] i.e. [lon, lat, date]
nc_close(nc)

cat("ffdi dims (ncdf4):", paste(dim(ffdi_arr), collapse = " x "), "\n")
# Expect: 886 x 691 x 146

# ── 2. Benchmark events — fire days only ────────────────────────────────────
bench <- read_csv("data/export/fig_benchmarks.csv", show_col_types = FALSE) |>
  mutate(date = as.Date(date))

# Exclude non-fire events
exclude <- c("TC Yasi", "East-coast floods 2022")
fire_bench <- bench |> filter(!name %in% exclude)
cat("Fire benchmark events:", nrow(fire_bench), "\n")
# Expect 10

# ── 3. Build long data frame ─────────────────────────────────────────────────
# For each benchmark day, extract the lon×lat slice and reshape to tidy rows.
# Drop NA (ocean) rows to keep memory manageable (~6M → ~2M rows).

# expand_grid(lat, lon): lat is leftmost → lon varies fastest (R rightmost varies fastest)
# as.vector() on matrix [886 lon × 691 lat]: col-major → row (lon) index varies fastest
# So both use lon-varies-fastest ordering — they match.
grid <- expand_grid(lat = lat, lon = lon)  # 691*886 = 611,726 rows; lon varies fastest

df_list <- lapply(seq_len(nrow(fire_bench)), function(j) {
  d   <- fire_bench$date[j]
  nm  <- fire_bench$name[j]
  di  <- match(d, dates)
  if (is.na(di)) {
    warning("Date not found in nc: ", d)
    return(NULL)
  }
  # ncdf4 dim order [lon=886, lat=691, date=146]
  # slice_mat is [886 lon × 691 lat]; as.vector() = col-major → lon varies fastest
  slice_mat <- ffdi_arr[, , di]          # matrix [886 × 691]
  vals      <- as.vector(slice_mat)      # lon varies fastest — matches expand_grid(lat, lon)
  d_grid    <- grid
  d_grid$ffdi <- vals
  d_grid$date <- d
  d_grid$name <- nm
  d_grid[!is.na(d_grid$ffdi), ]         # drop ocean NAs
})

df <- bind_rows(df_list)
cat("Rows in plot data frame:", nrow(df), "\n")

# ── 4. Facet label ──────────────────────────────────────────────────────────
df <- df |>
  mutate(panel_label = paste0(name, "\n", format(date, "%d %b %Y")))

# Order panels by date
panel_levels <- df |>
  distinct(date, panel_label) |>
  arrange(date) |>
  pull(panel_label)
df$panel_label <- factor(df$panel_label, levels = panel_levels)

# ── 5. Coastline ─────────────────────────────────────────────────────────────
aus <- ne_countries(country = "Australia", scale = "medium", returnclass = "sf")

# ── 6. Plot ──────────────────────────────────────────────────────────────────
p <- ggplot(df) +
  geom_raster(aes(lon, lat, fill = pmin(ffdi, 100))) +
  geom_sf(data = aus, fill = NA, colour = "grey30", linewidth = 0.2,
          inherit.aes = FALSE) +
  scale_fill_viridis_c(
    option = "inferno",
    name   = "FFDI",
    limits = c(0, 100),
    breaks = c(0, 25, 50, 75, 100),
    labels = c("0", "25", "50 Severe", "75 Extreme", "100+"),
    oob    = scales::squish
  ) +
  coord_sf(xlim = c(112, 155), ylim = c(-44, -9), expand = FALSE) +
  facet_wrap(~panel_label, ncol = 5) +
  labs(
    x     = NULL,
    y     = NULL,
    title = "Fire-danger footprint on fire benchmark demand days"
  ) +
  theme_minimal(base_size = 9) +
  theme(
    axis.text    = element_blank(),
    panel.grid   = element_blank(),
    strip.text   = element_text(size = 7.5, lineheight = 1.1)
  )

# ── 7. Save ──────────────────────────────────────────────────────────────────
dir.create("R/figs", showWarnings = FALSE, recursive = TRUE)
ggsave("R/figs/fig_ffdi_maps.png", p, width = 11, height = 5.5, dpi = 300)
cat("wrote R/figs/fig_ffdi_maps.png\n")
