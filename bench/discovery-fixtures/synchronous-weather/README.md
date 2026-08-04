# Synchronous weather context fixture

This is a bounded source/build descriptor fixture for the M7 Quality Context
Graph slice. It contains a provider boundary and a critical UI-style consumer;
it is deliberately neutral about whether any defect exists.

The fixture exposes:

- `WeatherService.kt`: provider/API and operation boundary;
- `SystemUiWeatherConsumer.kt`: synchronous consumer on a UI-style path;
- `build-metadata.json`: static build/package provenance;
- `context-manifest.json`: facts, nodes, directed edges, and explicit unknowns.

The manifest does not contain an expected verdict, a prescribed Journey, or a
hidden defect label. It can be collected with either a `ChangeTarget` or a
`ProjectTarget`; the target only binds the graph snapshot identity.
