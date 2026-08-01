# Evaluation Results

Generated: 2026-08-01T15:50:09

## Retrieval Evaluation

No LLM call — does keyword retrieval route each topic to its expected source document?

| Topic | Expected Source | Retrieved Sources | Hit |
|---|---|---|---|
| airspace | AIRSPACE.md | AIRSPACE.md | ✅ |
| weather | WEATHER.md | WEATHER.md | ✅ |
| operations | OPERATIONS.md | OPERATIONS.md | ✅ |
| certification | CERTIFICATION_AND_REGISTRATION.md | CERTIFICATION_AND_REGISTRATION.md | ✅ |

**Hit rate: 100%**

## Generation Reliability Evaluation (mode: offline fixtures)

| Topic | Success | Confidence Score | Attempts Used | Error |
|---|---|---|---|---|
| airspace | ✅ | 100 | 1 | — |
| weather | ✅ | 100 | 3 | — |
| operations | ✅ | 100 | 1 | — |
| certification | ✅ | 100 | 1 | — |

**Success rate: 100%**
**Average confidence score (successful runs): 100/100**

Note: the `weather` topic's offline fixture deliberately queues a schema-invalid response, then a schema-valid response that cites a document never retrieved for this topic, before a grounded response, to demonstrate that both validation layers actually reject bad output rather than always passing on the first try. See OFFLINE_FIXTURES in evaluation.py.
