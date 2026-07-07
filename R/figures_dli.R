# DLI figures. Run: /opt/anaconda3/envs/rfigs/bin/Rscript R/figures_dli.R
library(tidyverse)
library(sf)
library(rnaturalearth)

dir.create("R/figs", showWarnings = FALSE, recursive = TRUE)

dli   <- read_csv("data/export/fig_dli_daily.csv",    show_col_types = FALSE)
bench <- read_csv("data/export/fig_benchmarks.csv",   show_col_types = FALSE)
hs    <- read_csv("data/export/fig_hotspots_days.csv", show_col_types = FALSE)

# Fix tier factor so facets run left-right = Tier 3 (oldest) -> Tier 1 (newest)
tier_labels <- c(`3` = "Tier 3 (polygons)",
                 `2` = "Tier 2 (MODIS)",
                 `1` = "Tier 1 (VIIRS+MODIS)")
dli   <- dli   |> mutate(confidence_tier = factor(confidence_tier, levels = c(3, 2, 1)),
                          date = as.Date(date))
bench <- bench |> mutate(confidence_tier = factor(confidence_tier, levels = c(3, 2, 1)),
                          date = as.Date(date))

# ---- Figure 1: DLI daily series with benchmark events -----------------------
# Assign chronological number labels 1-12, sorted globally by date.
bench <- bench |> arrange(date) |> mutate(event_num = row_number())

# Detect adjacent events within same tier (within 180 days) and nudge x slightly
# so numbers don't sit directly on top of each other. Y is fixed at 1.03.
bench <- bench |>
  arrange(confidence_tier, date) |>
  group_by(confidence_tier) |>
  mutate(
    prev_date = lag(date),
    days_gap  = as.numeric(date - lag(date)),
    # nudge every other close pair: push even-numbered colliders right by 90 days
    x_nudge   = if_else(!is.na(days_gap) & days_gap < 150 & (row_number() %% 2 == 0),
                         as.numeric(date) + 90, as.numeric(date)),
    label_x   = as.Date(x_nudge, origin = "1970-01-01")
  ) |>
  ungroup()

# Compute 90-day centred rolling mean using base R stats::filter (triangular
# weights would need more code; use a simple uniform window).
# stats::filter returns a ts object; convert back to vector.
half_w <- 45L  # half-window => 91-point window
roll_mean_uniform <- function(x, half_w) {
  n   <- length(x)
  w   <- 2L * half_w + 1L
  flt <- rep(1 / w, w)
  as.numeric(stats::filter(x, flt, sides = 2))
}

dli <- dli |>
  arrange(confidence_tier, date) |>
  group_by(confidence_tier) |>
  mutate(dli_roll = roll_mean_uniform(dli, half_w)) |>
  ungroup()

# Build caption key: "1 Name · 2 Name · ..."  wrapped at ~90 chars
bench_sorted <- bench |> arrange(event_num)
key_parts    <- paste0(bench_sorted$event_num, " ", bench_sorted$name)
# Join with interpunct, wrap into two lines at roughly the midpoint
n_half   <- ceiling(nrow(bench_sorted) / 2)
line1    <- paste(key_parts[seq_len(n_half)],       collapse = " · ")
line2    <- paste(key_parts[seq(n_half + 1, nrow(bench_sorted))], collapse = " · ")
cap_text <- paste0(line1, "\n", line2)

p1 <- ggplot(dli, aes(date, dli)) +
  # Daily: thin light grey
  geom_line(linewidth = 0.2, colour = "grey70") +
  # 90-day rolling mean: steelblue, clearly visible
  geom_line(aes(y = dli_roll), linewidth = 0.7, colour = "steelblue4", na.rm = TRUE) +
  # Benchmark vlines: firebrick dashed
  geom_vline(data = bench, aes(xintercept = date),
             linetype = "dashed", colour = "firebrick", alpha = 0.6, linewidth = 0.35) +
  # Number labels: bold, no rotation, just above series at y = 1.03
  geom_text(data = bench, aes(x = label_x, y = 1.03, label = event_num),
            size = 2.8, fontface = "bold", colour = "firebrick", vjust = 0) +
  facet_grid(. ~ confidence_tier, scales = "free_x", space = "free_x",
             labeller = labeller(confidence_tier = tier_labels)) +
  scale_y_continuous(limits = c(0, 1.06), breaks = c(0, 0.25, 0.5, 0.75, 1)) +
  coord_cartesian(clip = "off") +
  labs(x = NULL, y = "Demand Load Index",
       title = "Daily national Demand Load Index, 1979–present",
       subtitle = "Grey: daily DLI. Coloured line: 90-day rolling mean. Numbered dashed lines: the 12 benchmark validation events (see key below).",
       caption = cap_text) +
  theme_minimal(base_size = 9) +
  theme(
    plot.caption      = element_text(size = 7.5, colour = "grey30", hjust = 0,
                                     margin = margin(t = 6)),
    plot.subtitle     = element_text(size = 8,   colour = "grey40"),
    panel.spacing.x   = unit(0.8, "lines"),
    strip.text        = element_text(size = 8.5, face = "bold"),
    axis.text.y       = element_text(size = 8),
    axis.text.x       = element_text(size = 7.5)
  )
ggsave("R/figs/fig_dli_timeseries.png", p1, width = 12, height = 4, dpi = 300)

# ---- Figure 2: hotspot maps on landmark demand days -------------------------
aus <- ne_countries(country = "Australia", scale = "medium", returnclass = "sf")

labels <- bench |> select(date, name)
hs2 <- hs |> left_join(labels, by = "date") |>
  mutate(panel = ifelse(is.na(name),
                        format(date, "%d %b %Y"),
                        paste0(name, "\n", format(date, "%d %b %Y"))))

p2 <- ggplot() +
  geom_sf(data = aus, fill = "grey95", colour = "grey60", linewidth = 0.2) +
  geom_point(data = hs2, aes(lon, lat, size = frp),
             colour = "orangered", alpha = 0.35, stroke = 0) +
  scale_size_area(max_size = 3, name = "FRP (MW)") +
  coord_sf(xlim = c(112, 155), ylim = c(-44, -9)) +
  facet_wrap(~panel, ncol = 4) +
  labs(x = NULL, y = NULL,
       title = "Satellite fire detections on landmark demand days") +
  theme_minimal(base_size = 9) +
  theme(axis.text = element_blank(), panel.grid = element_blank())
ggsave("R/figs/fig_hotspot_maps.png", p2, width = 11, height = 6, dpi = 300)

cat("wrote R/figs/fig_dli_timeseries.png and fig_hotspot_maps.png\n")
