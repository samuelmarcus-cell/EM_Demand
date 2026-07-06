# Fires x SWT — statistical figures in ggplot2.
# Run: /opt/anaconda3/envs/rfigs/bin/Rscript figures.R
suppressMessages(library(tidyverse))

base <- "/Users/smar0095/Fires_SWTs/R"
figs <- file.path(base, "figs"); dir.create(figs, showWarnings = FALSE)

elev_col <- "#c0392b"; supp_col <- "#2c6fbb"; ns_col <- "grey70"
theme_set(theme_bw(base_size = 12))

# ---- Figure 1: SWT-level relative risk of a multi-state fire day (Step 2) ----
swt <- read_csv(file.path(base, "swt_rr.csv"), show_col_types = FALSE) |>
  mutate(cat = case_when(sig_fdr & RR_mean > 1 ~ "Elevated (FDR)",
                         sig_fdr & RR_mean < 1 ~ "Suppressed (FDR)",
                         TRUE ~ "n.s."),
         assigned_SWT = fct_reorder(assigned_SWT, RR_mean))

p1 <- ggplot(swt, aes(RR_mean, assigned_SWT, colour = cat)) +
  geom_vline(xintercept = 1, linetype = "dashed", colour = "grey50") +
  geom_segment(aes(x = CI_low, xend = CI_high, yend = assigned_SWT), linewidth = 0.5) +
  geom_point(size = 2) +
  scale_colour_manual(values = c("Elevated (FDR)" = elev_col,
                                 "Suppressed (FDR)" = supp_col, "n.s." = ns_col)) +
  labs(x = "Relative risk of a >=2-state fire day (seasonally matched)",
       y = NULL, colour = NULL, title = "Multi-state fire days by synoptic weather type") +
  theme(legend.position = "top")
ggsave(file.path(figs, "fig_swt_rr.png"), p1, width = 7, height = 8, dpi = 200)

# ---- Figure 2: spatial spread beyond fire propensity (Step 4) ----
s4 <- read_csv(file.path(base, "step4_distance.csv"), show_col_types = FALSE) |>
  mutate(cat = case_when(sig_fdr & excess > 0 ~ "More dispersed (FDR)",
                         sig_fdr & excess < 0 ~ "More clustered (FDR)",
                         TRUE ~ "n.s."),
         assigned_SWT = fct_reorder(assigned_SWT, excess))

p2 <- ggplot(s4, aes(excess, assigned_SWT, fill = cat)) +
  geom_vline(xintercept = 0, linetype = "dashed", colour = "grey50") +
  geom_col() +
  scale_fill_manual(values = c("More dispersed (FDR)" = elev_col,
                               "More clustered (FDR)" = supp_col, "n.s." = ns_col)) +
  labs(x = "Excess mean pairwise distance vs N+season-matched null (km)\n(>0 = more dispersed = synchronisation)",
       y = NULL, fill = NULL, title = "Spatial spread beyond fire propensity (Step 4)") +
  theme(legend.position = "top")
ggsave(file.path(figs, "fig_step4_distance.png"), p2, width = 7, height = 8, dpi = 200)

# ---- Figure 3: region-pair co-occurrence excess heatmap (Step 5) ----
p5 <- read_csv(file.path(base, "step5_pairs.csv"), show_col_types = FALSE) |>
  mutate(star = ifelse(sig_fdr, "*", ""),
         assigned_SWT = factor(assigned_SWT, levels = c("FH-B", "WH-A", "TH-C", "WCT-B")),
         pair = fct_reorder(pair, abs(excess), .fun = max))

p3 <- ggplot(p5, aes(assigned_SWT, pair, fill = excess)) +
  geom_tile(colour = "white") +
  geom_text(aes(label = star), size = 6, vjust = 0.78) +
  scale_fill_gradient2(low = supp_col, mid = "white", high = elev_col, midpoint = 0) +
  labs(x = NULL, y = "state pair", fill = "excess\nco-occur.",
       title = "Region-pair co-occurrence excess (Step 5)",
       subtitle = "* = FDR-significant;  red = burn together more than chance") +
  theme_minimal(base_size = 12)
ggsave(file.path(figs, "fig_step5_pairs.png"), p3, width = 5.5, height = 7, dpi = 200)

cat("wrote 3 figures to", figs, "\n")
