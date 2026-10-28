# Model governance

`training/model_registry.json` is the source of truth. `configured` means a run can be started;
`not_trained` means no adapter exists; `validated` requires a recorded config, environment, adapter
hash and frozen-blind report. Never infer a performance claim from a config file.

