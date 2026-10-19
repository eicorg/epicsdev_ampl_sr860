# EPICS PVAccess server for SR860. UNDER DEVELOPMENT.

This server communicates with a [Stanford Research Systems SR860 lock-in
amplifier](https://www.thinksrs.com/products/sr860.html?utm_source=Google&utm_medium=cpc&utm_content=809725910606&utm_term=sr860%20lock%20in%20amplifier&utm_campaign=Google:%20193962822902:&wv_initiative=Google:%20193962822902&wv_audience=193962822902&gad_source=1&gad_campaignid=23874533965&gbraid=0AAAAAD_kyf2IANjMNzkTVMzQVDyxfhY6i&gclid=CjwKCAjw_9bWBhBGEiwAomyTItwj5fqJoeKEuBpZ_K98z5R0htictGiJAR7uk1az9sd7rjXKnR5lQBoCWtYQAvD_BwE) over VISA. Install the project dependencies and provide a VISA
resource string when starting the server:

```sh
uv run python -m epicsdev_ampl_sr860 --resource 'USB0::...::INSTR'
```

The server publishes synchronized `x`, `y`, `r`, and `theta` measurements and
provides PVs for the reference source and frequency, phase, input mode and
configuration, sensitivity, filter settings, and sine output amplitude. The
`instrCmdS`/`instrCmdR` PVs provide a direct SR860 command interface.

Instrument commands and supported setting ranges follow the SR860
Programming Manual.
