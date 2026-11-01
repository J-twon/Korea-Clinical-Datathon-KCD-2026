# Guideline vector store (BGE-M3, 1024-d, cosine)

| Folder | Source PDFs | Chunks | Text included |
|---|---|---|---|
| KR_GUIDE | K02 (KDCA/KSAT CAP), K04 (KDCA/KSAT UTI) | 95 | no — copyrighted; `text` emptied, `file`/`page` kept |
| US_GUIDE | M03 (ATS/IDSA CAP 2019), M04 (IDSA CAP pathway), M07 (IDSA cUTI 2025) | 226 | no — copyrighted; `text` emptied, `file`/`page` kept |
| WHO_GUIDE | W01 (WHO AWaRe antibiotic book 2022), W02 (WHO AWaRe classification 2025) | 1,964 | yes — WHO, CC BY-NC-SA 3.0 IGO |

`vectors.npy` holds one 1024-d embedding per line of `chunks.jsonl` (same order). Chunks are 1,000 characters with 200-character overlap, split within pages.
To use KR_GUIDE or US_GUIDE, obtain the PDFs from the issuers, extract page text (`pdftotext -layout`), and refill `text` for each chunk from its `file` and `page`; retrieval ranking works without the text.
