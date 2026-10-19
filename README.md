# SR860 EPICS PVAccess server. UNDER DEVELOPMENT.

This server communicates with a Stanford Research Systems SR860 lock-in
amplifier over VISA. Install the project dependencies and provide a VISA
resource string when starting the server:

```sh
uv run python -m epicsdev_ampl_sr860 --resource 'USB0::...::INSTR'
```

The selected PyVISA backend must support the configured resource (for example,
NI-VISA or `pyvisa-py`).

The server publishes synchronized `x`, `y`, `r`, and `theta` measurements and
provides PVs for the reference source and frequency, phase, input mode and
configuration, sensitivity, filter settings, and sine output amplitude. The
`instrCmdS`/`instrCmdR` PVs provide a direct SR860 command interface.

Instrument commands and supported setting ranges follow the SR860
Programming Manual in [`misc/programming_manual.pdf`](misc/programming_manual.pdf).
