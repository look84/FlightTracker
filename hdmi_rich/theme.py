"""
Air-traffic-control colour palette.

Pure black background with phosphor-green primary data, amber accent for
labels/chrome, dim grey for grids/inactive text, red for warnings.  Every
scene draws with these; no per-scene palette overrides.
"""

BACKGROUND = (0, 0, 0)
PRIMARY = (0, 255, 65)      # phosphor green - live telemetry, radar sweep
ACCENT = (255, 170, 0)      # amber - labels, chrome, headers
DIM = (74, 74, 74)          # grey - grid lines, inactive rings
FAINT = (110, 90, 20)       # dim amber - secondary labels, ticker background
WARNING = (255, 36, 0)      # red - alerts, errors
INACTIVE = (60, 60, 60)     # very dim - unpopulated fields
WHITE = (240, 240, 240)     # neutral text on the rare occasion it's needed
