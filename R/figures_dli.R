# DLI figures. Run: /opt/anaconda3/envs/rfigs/bin/Rscript R/figures_dli.R
library(tidyverse)
library(sf)
library(rnaturalearth)

dir.create("R/figs", showWarnings = FALSE, recursive = TRUE)

dli   <- read_csv("data/export/fig_dli_daily.csv",    show_col_types = FALSE)
bench <- read_csv("data/export/fig_benchmarks.csv",   show_col_types = FALSE)
hs    <- read_csv("data/export/fig_hotspots_days.csv", show_col_types = FALSE)

# Fix tier factor so facets run left→right = Tier 3 (oldest) → Tier 1 (newest)
tier_labels <- c(`3` = "Tier 3 (polygons)",
                 `2` = "Tier 2 (MODIS)",
                 `1` = "Tier 1 (VIIRS+MODIS)")
dli   <- dli   |> mutate(confidence_tier = factor(confidence_tier, levels = c(3, 2, 1)))
bench <- bench |> mutate(confidence_tier = factor(confidence_tier, levels = c(3, 2, 1)))

# ---- Figure 1: DLI daily series with benchmark events -----------------------
# ggrepel is NOT installed in this env; stagger y-positions within each tier
# to avoid label overprinting (Tier 1 has 6 events in a narrow window).
# Three y-levels per tier, assigned by event order within tier.
bench <- bench |>
  arrange(confidence_tier, date) |>
  group_by(confidence_tier) |>
  mutate(
    label_y = c(1.05, 1.20, 1.35)[((row_number() - 1) %% 3) + 1]
  ) |>
  ungroup()

p1 <- ggplot(dli, aes(date, dli)) +
  geom_line(linewidth = 0.15, colour = "grey40") +
  geom_vline(data = bench, aes(xintercept = date),
             linetype = "dashed", colour = "firebrick", linewidth = 0.3) +
  geom_text(data = bench, aes(date, label_y, label = name),
            angle = 90, size = 2.4, hjust = 0, colour = "firebrick") +
  facet_grid(. ~ confidence_tier, scales = "free_x", space = "free_x",
             labeller = labeller(confidence_tier = tier_labels)) +
  scale_y_continuous(limits = c(0, 1.70), breaks = seq(0, 1, 0.25)) +
  coord_cartesian(clip = "off") +
  labs(x = NULL, y = "Demand Load Index",
       title = "Daily national Demand Load Index, 1979–present",
       subtitle = "Dashed lines: the 12 benchmark validation events") +
  theme_minimal(base_size = 9)
ggsave("R/figs/fig_dli_timeseries.png", p1, width = 13, height = 5, dpi = 300)

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
