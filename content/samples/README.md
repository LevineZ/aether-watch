# Sample NetCDF

AetherWatch does not commit a binary `.nc` file. Generate one from Admin → **Generate demo NetCDF**, which calls `POST /api/admin/datasets/demo` and runs `NcIngestActor` → `NcTileActor`.

The demo field is a synthetic 2 m temperature over China (`lat` 18–54°N, `lon` 73–135°E, one time step).
