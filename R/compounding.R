# R/compounding.R — state×hazard compounding figures (run via rfigs env Rscript)
library(ggplot2)
library(dplyr)
library(readr)
library(stringr)

derived <- "data/derived"
figs <- "R/figs"
dir.create(figs, showWarnings = FALSE, recursive = TRUE)

ratios <- read_csv(file.path(derived, "compounding_ratios.csv"), show_col_types = FALSE)
samples <- read_csv(file.path(derived, "compounding_null_samples.csv"), show_col_types = FALSE)

# --- fig 1: observed vs null distributions (headline: 0.95 / 300 km) ---
lab <- function(stat, k) {
  ifelse(stat == "cross", "cross-hazard day\n(fire + tc, different states)",
         sprintf(">= %d states, %s", k, stat))
}
s <- samples |> filter(flag_threshold == 0.95, radius_km == 300) |>
  mutate(panel = lab(statistic, threshold), freq_yr = frequency * 365)
o <- ratios |> filter(flag_threshold == 0.95, radius_km == 300) |>
  mutate(panel = lab(statistic, threshold), obs_yr = observed * 365)

p1 <- ggplot(s, aes(freq_yr)) +
  geom_histogram(bins = 40, fill = "grey70", colour = NA) +
  geom_vline(data = o, aes(xintercept = obs_yr), colour = "firebrick", linewidth = 0.8) +
  facet_wrap(~panel, scales = "free") +
  labs(x = "days per year", y = "shuffles (of 1,000)",
       title = "Observed spatial hazard-load compounding vs independence null",
       subtitle = str_wrap(paste(
         "Red line = observed frequency; grey = 1,000 year-block shuffles",
         "(states' years permuted independently; fire within confidence tier).",
         "High load = within-(state, month[, tier]) percentile >= 0.95."), 100)) +
  theme_minimal(base_size = 11)
ggsave(file.path(figs, "fig_compounding_null.png"), p1,
       width = 10, height = 6, dpi = 200)

# --- fig 2: state×state co-occurrence matrix ---
cooc <- read_csv(file.path(derived, "state_cooccurrence.csv"), show_col_types = FALSE) |>
  filter(state_a != state_b)
p2 <- ggplot(cooc, aes(state_a, state_b, fill = n_days)) +
  geom_tile() +
  geom_text(aes(label = n_days), size = 3) +
  facet_wrap(~hazard) +
  scale_fill_gradient(low = "white", high = "firebrick") +
  labs(x = NULL, y = NULL, fill = "joint high-load days",
       title = "Days both states under high hazard load (flag >= 0.95)") +
  theme_minimal(base_size = 11)
ggsave(file.path(figs, "fig_state_cooccurrence.png"), p2,
       width = 10, height = 5, dpi = 200)

# --- fig 3: timeline strip of top compound days ---
top <- read_csv(file.path(derived, "compound_days_top.csv"), show_col_types = FALSE)
p3 <- ggplot(top, aes(date, state, colour = layer)) +
  geom_point(size = 3) +
  scale_colour_manual(values = c(fire = "firebrick", tc = "steelblue")) +
  labs(x = NULL, y = NULL, colour = "hazard",
       title = "Top compound days: which states, which hazards",
       subtitle = "30 days with the most simultaneous high-hazard-load cells") +
  theme_minimal(base_size = 11)
ggsave(file.path(figs, "fig_compound_days_timeline.png"), p3,
       width = 10, height = 4, dpi = 200)

cat("wrote 3 figures to", figs, "\n")
