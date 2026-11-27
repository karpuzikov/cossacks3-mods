Cossacks 3 Startup Fix

Shortens long config tool and game startup.
- Removes the DWM8And16BitMitigation Windows compatibility setting.
- Patches 2 bytes in config.exe and cossacks.exe to skip testing every
  display mode (backups are saved in startup_fix_backup).

Use: close the game, run "Apply fix.cmd". Undo with "Undo fix.cmd".
Compatibility setting only: "Apply fix.cmd" -NoPatch

Steam updates or file verification remove the patch; run it again.
Cause confirmed on one PC only. Multiplayer not tested.
