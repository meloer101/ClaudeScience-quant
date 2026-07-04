# Changelog

## Unreleased

- Changed default execution fill from `close_t` to `open_t+1`.
- Explicit `close_t` runs now receive a Reviewer warning because same-close fills are optimistic.
- Fixed crypto perpetual funding cost estimation: funding history is paginated and intraday funding rows are aggregated into rebalance holding periods.
