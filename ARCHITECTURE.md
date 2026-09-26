# L3B Architecture Record

Team phải cập nhật tài liệu này cùng source. Mục tiêu là mô tả quyết định có thể kiểm chứng, không ghi prompt bí mật hoặc chain-of-thought.

## 1. System overview

Vẽ hoặc mô tả luồng từ input/candidate resolution đến MCP investigation, specialist agents, conflict resolver, verifier, output và trace.

```text

                                    Coordinator
                                        |
         _______________________________|_________________________________
         |                               |                              |
   Order Agent                      Payment Agent                 Shipment Agent
        │                                  |                            |
        └────────────────────────────────────────────────────────────────
                                  MCP Evidence Collector
                                            |
                                            |
                                        Policy Agent
                                            |
                                            |
                                        Verifer Agent
                                            |
                                            |
                                        End output
```

## 2. Agent ownership

| Actor | Input | Trách nhiệm | Tool permission | Output/handoff |
| --- | --- | --- | --- | --- |
| Entity/customer | claimed_order_id, candidate_order_ids, customer_unique_id_hint | Xác minh candidate nào là order thật; lấy lịch sử khách hàng để cross-check | get_order, get_customer_history | entity_resolution, customer_context → Coordinator |
| Coordinator | case, kết quả các specialist | Điều phối handoff, gộp kết quả theo case_id, không tự suy luận nghiệp vụ | (không gọi MCP trực tiếp) | Gọi Policy Agent, Verifier; tổng hợp output cuối |
| Order/product | resolved_order_id | Lấy trạng thái đơn hàng, danh sách item, seller, thông tin sản phẩm | get_order, get_order_items, get_product_context, get_sellers | affected_entities.item_ids/seller_ids → Coordinator, Policy Agent |
| Shipment | resolved_order_id | Xác định shipment_analysis.verdict (on_time/seller_delay/logistics_delay/lost/returned) dựa trên mốc thời gian giao/nhận | get_shipment_summary | 	shipment_analysis → Coordinator, Policy Agent |
| Payment/refund | resolved_order_id | 	Đối chiếu capture/refund, tính captured/refunded/refundable_total_brl | get_order_payments, get_payment_timeline, get_refund_timeline | payment_analysis, dữ liệu đầu vào cho financial_resolution |
| Policy | 	policy_version, kết quả 3 specialist | Áp business rule chọn primary_issue/case_status, giải quyết source conflict, tính resolution_actions | get_policy | assessment, root_cause_analysis, data_conflicts, resolution_actions |
| Conflict resolver | Evidence mâu thuẫn giữa các specialist | Chọn selected_source theo thứ tự ưu tiên, ghi resolution_code | (không gọi thêm MCP, chỉ dùng evidence đã thu thập trong case) | data_conflicts[] |
| Verifier | Output nháp + toàn bộ evidence_refs đã thu thập | Kiểm schema, entity scope, evidence ownership, claim linkage, timeline, payment totals, confidence bounds | (không gọi MCP, chỉ đọc lại evidence trong bộ nhớ case) | verification_completed; nếu fail → trả case cho Coordinator để re-investigate |

Áp dụng least privilege; tool discovery không đồng nghĩa mọi actor đều được gọi mọi tool.

## 3. Entity resolution và A2A protocol

Mô tả cách xếp hạng/reject candidate, confidence threshold, message envelope, correlation theo `case_id`, điều kiện handoff, timeout và cách tránh vòng lặp. Không trace nội dung suy luận riêng.

## 4. Evidence và conflict lifecycle

Mô tả cách validate MCP response, lưu `evidence_ref`, chọn source theo policy, biểu diễn unresolved conflict, map evidence vào claim/output và emit `tool_result_consumed`. Evidence không được tái sử dụng giữa các case.

## 5. Failure and efficiency policy

| Failure | Retry budget | Fallback | Trace event/code |
| --- | ---: | --- | --- |
| MCP timeout | 1 lần | Domain đó đặt insufficient_evidence; timeline_complete=false nếu là shipment | Không emit tool_result_consumed nếu vẫn fail; ghi nhận trong assessment.secondary_issues |
| Entity not found/ambiguous | TODO | TODO | TODO |
| Source conflict | TODO | TODO | TODO |
| Invalid specialist result | TODO | TODO | TODO |

Nêu query budget/cache strategy để tránh gọi lặp và quét rộng. Retry phải có giới hạn, idempotent và không biến missing evidence thành dữ liệu phỏng đoán.

## 6. Verification invariants

Liệt kê kiểm tra trước finalize: schema, entity scope, rejected candidates, evidence ownership, claim linkage, timeline, payment/refund totals, source precedence, responsibility/action consistency và confidence bounds.

## 7. Reproducibility

Ghi model/config, dependency pinning, concurrency limit, random seed (nếu có), lệnh chạy và giới hạn tài nguyên. Không ghi API key.
