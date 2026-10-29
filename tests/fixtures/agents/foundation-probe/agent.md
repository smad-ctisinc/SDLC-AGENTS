# Foundation Probe

This synthetic role exercises contract validation only. It is not an SDLC agent
and has no executable implementation.

Given a non-empty `project_id`, its future test executor would return that same
identifier and `status: ok`. It must not read files, invoke tools, call a model,
or modify external state. The paired `contract.yaml` defines its data shapes.
