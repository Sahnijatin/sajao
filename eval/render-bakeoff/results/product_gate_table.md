# Product fidelity per version (DINOv3 gate)

Thresholds: silhouette >= 0.70, colour difference <= 10, DINOv3 embedding >= 0.475. Colour and look are scored against held-out listing photos (input photo, dimension drawings and detail crops excluded). Shape is scored against the code-made layout at the same camera. Rugs are unknown until the flat items check exists (SJ-150).

## Final run: gate-passing products only

| Design | Product | A | C1 | C2 | C3 | C3L | B open |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 41159566_best_value | rug (ikea_10629161) | unknown | unknown | unknown | unknown | unknown | unknown |
| 41159566_bold | Kairav Modern 2 Seater Wooden Sofa | pass | pass | pass | pass | pass | pass |
| 41159566_bold | NODELAND Coffee table | pass | fail: colour | pass | pass | pass | pass |
| 41159566_bold | SOTENÄS Armchair | pass | pass | pass | pass | pass | fail: shape |
| 41159566_bold | rug (ikea_50597318) | unknown | unknown | unknown | unknown | unknown | unknown |
| 41159566_best_match | GAMMALBYN 3-seat sofa | pass | pass | pass | pass | pass | pass |
| 41159566_best_match | Orwell Round Coffee Table (Honey F | pass | pass | pass | pass | pass | pass |
| 41159566_best_match | ÅRSUNDA Armchair | pass | pass | pass | pass | pass | fail: shape |
| 41159566_best_match | rug (ikea_20623074) | unknown | unknown | unknown | unknown | unknown | unknown |
| 0_best_value | rug (ikea_10629161) | unknown | unknown | unknown | unknown | unknown | unknown |
| 0_bold | Kairav Modern 2 Seater Wooden Sofa | pass | pass | pass | pass | pass | pass |
| 0_bold | NODELAND Coffee table | pass | pass | pass | fail: colour | fail: colour | fail: shape |
| 0_bold | SOTENÄS Armchair | pass | pass | pass | pass | pass | pass |
| 0_bold | rug (ikea_50597318) | unknown | unknown | unknown | unknown | unknown | unknown |
| 41159541_best_value | rug (ikea_10629161) | unknown | unknown | unknown | unknown | unknown | unknown |
| 0_best_match | GAMMALBYN 3-seat sofa | fail: colour | pass | pass | fail: colour | fail: colour | pass |
| 0_best_match | Orwell Round Coffee Table (Honey F | pass | pass | pass | pass | pass | pass |
| 0_best_match | ÅRSUNDA Armchair | fail: colour | pass | pass | pass | pass | pass |
| 0_best_match | rug (ikea_20623074) | unknown | unknown | unknown | unknown | unknown | unknown |
| 41159541_best_match | GAMMALBYN 3-seat sofa | fail: colour | pass | pass | fail: shape, colour | fail: colour | pass |
| 41159541_best_match | Orwell Round Coffee Table (Honey F | pass | pass | pass | pass | pass | pass |
| 41159541_best_match | ÅRSUNDA Armchair | pass | pass | pass | pass | pass | fail: shape |
| 41159541_best_match | rug (ikea_20623074) | unknown | unknown | unknown | unknown | unknown | unknown |
| 47331265_best_value | rug (ikea_10629161) | unknown | unknown | unknown | unknown | unknown | unknown |
| 47331265_best_value | wall_art | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 41159541_bold | Kairav Modern 2 Seater Wooden Sofa | pass | pass | pass | pass | pass | pass |
| 41159541_bold | NODELAND Coffee table | pass | pass | pass | pass | pass | fail: shape |
| 41159541_bold | SOTENÄS Armchair | pass | pass | pass | pass | pass | fail: shape |
| 41159541_bold | rug (ikea_50597318) | unknown | unknown | unknown | unknown | unknown | unknown |
| 47331265_best_match | GAMMALBYN 3-seat sofa | fail: colour | fail: colour | fail: colour | fail: colour | fail: colour | fail: colour |
| 47331265_best_match | Orwell Round Coffee Table (Honey F | pass | fail: colour | pass | pass | pass | pass |
| 47331265_best_match | ÅRSUNDA Armchair | pass | fail: shape | pass | pass | pass | fail: shape |
| 47331265_best_match | rug (ikea_20623074) | unknown | unknown | unknown | unknown | unknown | unknown |
| 47331265_best_match | wall_art | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 47331265_bold | Kairav Modern 2 Seater Wooden Sofa | fail: look | fail: shape | fail: shape | fail: look | fail: look | fail: shape |
| 47331265_bold | NODELAND Coffee table | pass | pass | pass | pass | pass | fail: shape |
| 47331265_bold | SOTENÄS Armchair | pass | pass | pass | pass | pass | fail: shape |
| 47331265_bold | rug (ikea_50597318) | unknown | unknown | unknown | unknown | unknown | unknown |

## Earlier run: before product swaps and brightness-only light (Gemini evidence)

| Design | Product | A | C3 | C3L | B open | B Gemini |
| --- | --- | --- | --- | --- | --- | --- |
| 41159566_best_value | rug (ikea_10629161) | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 41159566_best_value | PILSKOTT LED floor lamp | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 41159566_best_match | LANDSKRONA 3-seat sofa | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 41159566_best_match | BORGEBY Coffee table | pass | pass | pass | pass | pass |
| 41159566_best_match | SKÅLBODA Armchair | fail: look | fail: colour, look | fail: colour | fail: shape | fail: shape, colour |
| 41159566_best_match | rug (ikea_20623074) | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 41159566_best_match | PILSKOTT LED floor lamp | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 0_best_value | rug (ikea_10629161) | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 41159566_bold | Kairav Modern 2 Seater Wooden Sofa | pass | pass | pass | pass | pass |
| 41159566_bold | KRAGSTA Coffee table | pass | pass | pass | fail: shape | fail: shape |
| 41159566_bold | SOTENÄS Armchair | pass | pass | pass | fail: shape | fail: shape |
| 41159566_bold | rug (ikea_50597318) | pass | fail: look | fail: look | fail: shape, look | fail: shape |
| 41159566_bold | PILSKOTT LED floor lamp | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 0_best_match | UPPÅKRA 3-seat modular sofa | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 0_best_match | BORGEBY Coffee table | pass | pass | pass | fail: shape | fail: shape |
| 0_best_match | SKÅLBODA Armchair | pass | fail: colour | fail: colour | fail: colour | fail: shape, colour |
| 0_best_match | rug (ikea_20623074) | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 41159541_best_value | rug (ikea_10629161) | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 0_bold | Kairav Modern 2 Seater Wooden Sofa | pass | pass | pass | pass | pass |
| 0_bold | KRAGSTA Coffee table | fail: colour | fail: colour | fail: colour | fail: shape | fail: shape |
| 0_bold | SOTENÄS Armchair | pass | pass | pass | pass | pass |
| 0_bold | rug (ikea_50597318) | fail: look | fail: look | fail: look | fail: shape, look | fail: shape, colour, look |
| 41159541_best_match | LANDSKRONA 3-seat sofa | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 41159541_best_match | BORGEBY Coffee table | pass | pass | pass | pass | fail: shape |
| 41159541_best_match | SKÅLBODA Armchair | pass | pass | pass | fail: shape, colour | fail: shape |
| 41159541_best_match | rug (ikea_20623074) | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 41159541_bold | Kairav Modern 2 Seater Wooden Sofa | pass | pass | pass | pass | fail: shape |
| 41159541_bold | KRAGSTA Coffee table | pass | pass | pass | fail: shape | pass |
| 41159541_bold | SOTENÄS Armchair | pass | pass | pass | fail: shape | fail: shape, colour, look |
| 41159541_bold | rug (ikea_50597318) | fail: look | fail: colour, look | fail: look | fail: shape, look | fail: shape, look |
| 47331265_best_value | rug (ikea_10629161) | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 47331265_best_value | wall_art | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 47331265_best_match | LANDSKRONA 3-seat sofa | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 47331265_best_match | BORGEBY Coffee table | pass | pass | pass | fail: shape | fail: shape |
| 47331265_best_match | SKÅLBODA Armchair | pass | fail: colour | fail: colour | fail: shape, colour | fail: shape, colour |
| 47331265_best_match | rug (ikea_20623074) | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 47331265_best_match | wall_art | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
| 47331265_bold | Kairav Modern 2 Seater Wooden Sofa | pass | pass | pass | pass | pass |
| 47331265_bold | KRAGSTA Coffee table | pass | fail: colour | fail: colour | fail: shape | fail: shape |
| 47331265_bold | SOTENÄS Armchair | pass | pass | pass | fail: shape | fail: shape |
| 47331265_bold | rug (ikea_50597318) | fail: look | fail: look | fail: look | fail: shape, look | fail: shape, look |
| 47331265_bold | wall_art | unverifiable | unverifiable | unverifiable | unverifiable | unverifiable |
