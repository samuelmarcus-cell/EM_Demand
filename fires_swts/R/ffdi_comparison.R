# THE money shot: fire danger synchronises across states more than realized fire does.
# Run: /opt/anaconda3/envs/rfigs/bin/Rscript ffdi_comparison.R
suppressMessages(library(tidyverse))
base <- "/Users/smar0095/Fires_SWTs/R"; figs <- file.path(base, "figs")
dir.create(figs, showWarnings = FALSE, recursive = TRUE)
theme_set(theme_bw(base_size = 12))
HEAD <- c("FH-B", "WH-A", "TH-C", "WCT-B")
fire_col <- "#7f7f7f"; dang_col <- "#b2182b"

# ---- Panel A: per-SWT multi-state RR, realized fire -> fire danger ----
fire <- read_csv(file.path(base, "swt_rr.csv"), show_col_types = FALSE) |>
  transmute(swt = assigned_SWT, fire = RR_mean)
dang <- read_csv(file.path(base, "swt_danger_rr.csv"), show_col_types = FALSE) |>
  transmute(swt = assigned_SWT, danger = RR_mean, danger_sig = sig_fdr)
d <- inner_join(fire, dang, by = "swt") |>
  mutate(swt = fct_reorder(swt, danger),
         label = if_else(swt %in% HEAD, paste0(swt, " *"), as.character(swt)))
ylabs <- d |> arrange(swt) |> pull(label)

pA <- ggplot(d, aes(y = swt)) +
  geom_vline(xintercept = 1, linetype = "dashed", colour = "grey50") +
  geom_segment(aes(x = fire, xend = danger, yend = swt), colour = "grey75", linewidth = 0.7,
               arrow = arrow(length = unit(0.10, "cm"), type = "closed")) +
  geom_point(aes(x = fire,   colour = "Realized fire"),       size = 2.3) +
  geom_point(aes(x = danger, colour = "Fire danger (FFDI)"),  size = 2.3) +
  scale_colour_manual(values = c("Realized fire" = fire_col, "Fire danger (FFDI)" = dang_col),
                      name = NULL, breaks = c("Realized fire", "Fire danger (FFDI)")) +
  scale_y_discrete(labels = ylabs) +
  labs(title = "Fire DANGER synchronises across states more than realized fire",
       subtitle = "Multi-state (>=2) relative risk per SWT; arrow = realized fire -> danger.  * = headline regimes",
       x = "Relative risk of a multi-state day (RR = 1 -> as expected by chance)", y = NULL) +
  theme(legend.position = "top")
ggsave(file.path(figs, "fig_rr_fire_vs_danger.png"), pA, width = 8, height = 8, dpi = 150)
cat("wrote fig_rr_fire_vs_danger.png\n")

# ---- Panel B: count of FDR-significant 'together more than chance' region-pairs ----
np_fire <- read_csv(file.path(base, "step5_pairs.csv"), show_col_types = FALSE) |>
  filter(excess > 0, sig_fdr) |> nrow()
np_dang <- read_csv(file.path(base, "step8_danger_pairs.csv"), show_col_types = FALSE) |>
  filter(excess > 0, sig_fdr) |> nrow()
pairs <- tibble(metric = c("Realized fire", "Fire danger (FFDI)"), n = c(np_fire, np_dang)) |>
  mutate(metric = fct_relevel(metric, "Realized fire"))
pB <- ggplot(pairs, aes(metric, n, fill = metric)) +
  geom_col(width = 0.6) +
  geom_text(aes(label = n), vjust = -0.3, size = 5) +
  scale_fill_manual(values = c("Realized fire" = fire_col, "Fire danger (FFDI)" = dang_col), guide = "none") +
  labs(title = "State-pairs hot/burning together more than chance",
       subtitle = "FDR-significant pairs across the 4 headline SWTs (of 84 tested)",
       x = NULL, y = "# significant region-pairs") +
  expand_limits(y = max(pairs$n) * 1.15)
ggsave(file.path(figs, "fig_pairs_fire_vs_danger.png"), pB, width = 5, height = 4.5, dpi = 150)
cat(sprintf("wrote fig_pairs_fire_vs_danger.png  (fire=%d, danger=%d sig pairs)\n", np_fire, np_dang))
