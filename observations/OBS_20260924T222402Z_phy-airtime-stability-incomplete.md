# OBS SF7/BW250 CRC observations in sparse USER screening

Result: INCONCLUSIVE.

During bidirectional sparse screening on two clean, image-validated LoRa-Chatter nodes, SF7/BW250 produced repeated CRC errors at the B receiver for A→B USER payloads of 16 B and 32 B. The physical RF frames were 28 B and 44 B. Telemetry reported RSSI/SNR `-24/4` and `-25/3`, respectively. Each point was repeated to ten USER requests per direction; the affected logical deliveries eventually received matching ACKs. No cross-node USER TX overlap was observed in these points.

The run stopped before dense sweeps, airtime-matched controls, or PHY re-apply experiments, so this is a follow-up target rather than a root-cause finding. Raw CRC and retry telemetry is in [the associated RUN](../runs/RUN_20260924T222402Z_phy-airtime-stability-incomplete/REPORT.md), with complete forensic records in `serialterminal.log` around lines 4530, 4821, 5360, and 5715.

Run bundle: runs/RUN_20260924T222402Z_phy-airtime-stability-incomplete/
