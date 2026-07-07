# DRFA activation choropleth.
# Run: /opt/anaconda3/envs/rfigs/bin/Rscript R/drfa_map.R

library(tidyverse)
library(sf)

counts <- read_csv("data/export/fig_drfa_lga.csv", show_col_types = FALSE)
lga <- st_read("data/export/lga_boundaries.geojson", quiet = TRUE) |>
  left_join(counts, by = "lga_name")

p <- ggplot(lga) +
  geom_sf(aes(fill = n_activations), colour = NA) +
  scale_fill_viridis_c(
    name = "DRFA\nactivations",
    trans = "log1p",
    na.value = "grey92"
  ) +
  coord_sf(xlim = c(112, 155), ylim = c(-44, -9)) +
  labs(
    title = "Disaster-funding activations per Local Government Area, 2006–present",
    subtitle = paste0(
      "Count of DRFA event-activations; grey = never activated. ",
      "LGA 2025 boundaries (GDA2020); 100% of 522 DRFA LGAs matched (2 ABS-2025 renames applied)."
    )
  ) +
  theme_minimal(base_size = 9) +
  theme(axis.text = element_blank(), panel.grid = element_blank())

ggsave("R/figs/fig_drfa_choropleth.png", p, width = 8, height = 7, dpi = 300)
cat("wrote R/figs/fig_drfa_choropleth.png\n")
