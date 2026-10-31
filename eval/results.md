# Evaluation results

- Model: `gemini-3.5-flash-lite`
- Run: 2026-10-31 12:02, 145 s
- **Passed: 17 / 17** (failed 0, errors 0)

| Question | Category | Status | Tools called | Failed checks |
| --- | --- | --- | --- | --- |
| refund-cw1002 | refund | PASS | calculate_refund |  |
| refund-cw1007-exactly-48h | refund | PASS | get_booking, calculate_refund |  |
| refund-cw1010-exactly-24h | refund | PASS | get_booking, calculate_refund |  |
| refund-cw1003-zero-percent | refund | PASS | get_booking, calculate_refund |  |
| refund-cw1004-voucher | refund | PASS | get_booking, calculate_refund, search_policies, search_policies |  |
| not-cancellable-cw1008-in-progress | not_cancellable | PASS | get_booking, calculate_refund, search_policies |  |
| not-cancellable-cw1006-completed | not_cancellable | PASS | get_booking, calculate_refund |  |
| not-found-cw9999 | not_found | PASS | get_booking |  |
| booking-cw1001-facts | booking | PASS | get_booking |  |
| policy-saturday-hours | policy | PASS | search_policies |  |
| policy-ebike-day-price | policy | PASS | search_policies |  |
| policy-ebike-age-14 | policy | PASS | search_policies |  |
| policy-late-return-city | policy | PASS | search_policies, calculate_late_fee |  |
| refusal-general-knowledge | refusal | PASS |  |  |
| refusal-unrelated-task | refusal | PASS |  |  |
| refusal-not-in-documents-parking | refusal | PASS | search_policies, search_policies |  |
| invalid-id-12345 | not_found | PASS | get_booking |  |
