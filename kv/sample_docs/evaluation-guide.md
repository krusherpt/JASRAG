# Evaluation Guide

Retrieval quality should be measured with golden queries.

Each eval case should define a query and the expected title, source type, category, or content. The eval runner reports top1 and top3 hit rates.

Do not add more retrieval complexity until the eval results show which queries fail.
