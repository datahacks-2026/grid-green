# Related Work

GridGreen sits at the intersection of ML carbon estimation, grid-aware computing, and developer tooling.

## Runtime emission trackers

**CodeCarbon** ([Courty et al., 2021](https://codecarbon.io/)) measures emissions during script execution using hardware power models and grid intensity. It provides ground truth for short jobs but requires a completed run. GridGreen complements CodeCarbon with pre-execution estimates from static code analysis.

**Carbon Tracker** ([Anthony et al., 2020](https://arxiv.org/abs/2007.03081)) logs GPU power and carbon during training. Like CodeCarbon, it is reactive rather than predictive.

**experiment-impact-tracker** and datacenter telemetry (RAPL, DCGM) offer finer-grained measurements at the cost of instrumentation complexity.

## Estimation calculators

**Green Algorithms** ([Lannelongue et al., 2021](https://green-algorithms.org/)) estimates compute carbon from hardware, runtime, and location inputs supplied by the user. GridGreen infers workload parameters from code instead of manual form filling.

**eco2ai** monitors emissions during deep learning training and inference across frameworks.

**ML CO2 Impact** and similar calculators provide order-of-magnitude estimates without IDE integration.

## Grid-aware scheduling

Prior work on geographic load shifting and carbon-aware Kubernetes schedulers (e.g., postponing batch jobs to low-carbon windows) informs GridGreen's `find_clean_window` endpoint. GridGreen exposes this to individual developers via EIA-backed forecasts rather than cluster operators only.

## Model efficiency and recommendation

Model compression, distillation, and smaller-architecture selection are well studied. GridGreen's RAG corpus encodes curated model pairs with cited benchmark retention, making trade-offs explicit in the suggestion API.

## Agent and IDE integration

MCP (Model Context Protocol) enables coding agents to call structured tools. GridGreen exposes estimation, grid checks, and suggestions as MCP tools for Claude Desktop, Cursor, and similar clients.

## Positioning summary

| Tool | Timing | Input | Output |
|---|---|---|---|
| CodeCarbon | Post-run | Executed script | Measured emissions |
| Green Algorithms | Pre-run | User parameters | Estimate |
| GridGreen | Pre-run | Source code | Estimate + swaps + schedule window |

GridGreen's contribution is the **integration** of these capabilities in a single developer-facing system with documented methodology and optional runtime validation.
