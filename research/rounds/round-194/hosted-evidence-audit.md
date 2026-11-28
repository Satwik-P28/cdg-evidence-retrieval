# Hosted evidence preservation audit

Raw JSON extracted directly from completed successful hosted job logs, not reconstructed from tables. Source run IDs R188 46128177554, R190 46132408361, R193 46181949785. Each record carries original manifest, query hashes, storage and correctness counts. No source data copied. R193 all four real first-parent Git histories passed. Relative to R168 one-hop signed baseline, best path storage reduction: CPython 1683456 -> 1646592 B (2.19%); Git 2056192 -> 2015232 (1.99%); BIPs 1630208 -> 1593344 (2.26%); Kubernetes 991232 -> 974848 (1.65%). Best arm differs by corpus; post-hoc minima not a prospective policy result. R191/192 AP quota remains unresolved; R193 does not replace that missing evidence. All finalized archive subset only. Preserve these data; return to evidence retrieval in R194.

- R188 ap 74364: job 140927332088, 5 arms
- R188 clark 1161: job 140927332246, 5 arms
- R188 ap 10009: job 140927332435, 5 arms
- R190 clark 1161: job 140940246403, 5 arms
- R190 ap 10009: job 140940246594, 5 arms
- R190 ap 74364: job 140940246597, 5 arms
- R193 cpython 355: job 141093269608, 7 arms
- R193 gitdocs 667: job 141093269789, 7 arms
- R193 bips 395: job 141093269839, 7 arms
- R193 k8sdocs 378: job 141093269858, 7 arms
