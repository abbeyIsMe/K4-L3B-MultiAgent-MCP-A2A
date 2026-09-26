# L3B Architecture Record

Pha 2 định nghĩa ranh giới giữa coordinator và specialist. Module
`src/student_agent/state.py` chỉ chứa contract nội bộ; output cuối vẫn phải
tuân theo `contracts/schemas/l3b-output-v2.schema.json`.

## 1. Luồng A2A

```text
case input
    -> coordinator
    -> entity_customer
    -> order_product / shipment / payment_refund (song song khi đủ context)
    -> conflict_resolver (khi có mâu thuẫn)
    -> policy
    -> verifier
    -> coordinator finalize
```

Coordinator là router duy nhất. Mỗi specialist nhận một `SpecialistTask` và trả
`SpecialistResult`. Cả hai phải giữ nguyên `case_id` và `task_id`; coordinator
không ghép kết quả từ case khác.

Trace chỉ ghi sự kiện quan sát được qua `TraceWriter`. `WorkflowEvent` là adapter
nội bộ cho các field của `trace-event-v1.schema.json`; không có event schema
công khai thứ hai và không ghi prompt, chain-of-thought hay secret.

## 2. State và handoff contract

`InvestigationState` chứa tối thiểu:

- `case_id`, `input_case`: định danh và input gốc của case;
- `resolved_order_ids`, `rejected_candidates`: kết quả entity resolution;
- `evidence_refs`: tập evidence do MCP cấp, chỉ thuộc case hiện tại;
- `specialist_results`, `conflict_ids`: kết quả đã nhận và conflict cần xử lý;
- `status`: `received`, `investigating`, `ready_for_policy`,
  `ready_for_verification`, hoặc `finalized`.

`SpecialistTask` gồm `task_id`, `case_id`, `role`, `objective`, `allowed_tools`,
`context` và `attempt`. `SpecialistResult` gồm `task_id`, `case_id`, `role`,
`status`, `findings`, `evidence_refs`, `conflict_ids` và `error_code`.

Handoff phải truyền context tối thiểu cần cho task, không truyền suy luận riêng
hay toàn bộ state nếu không cần. Specialist chỉ được trả evidence reference do
Gateway cấp; không tự tạo hoặc sửa `evidence_ref`. Coordinator hợp nhất kết quả,
loại duplicate evidence và giữ liên kết claim → evidence khi tạo output ở Pha 3+.

## 3. Trách nhiệm và quyền MCP tối thiểu

Tool list dưới đây chỉ dùng tên từ discovery Pha 1. Tham số và điều kiện gọi
chưa được xác nhận, sẽ chốt ở Pha 3.

| Vai trò | Trách nhiệm | MCP tools tối thiểu |
| --- | --- | --- |
| Coordinator | Nhận case, tạo task, giới hạn ngân sách, hợp nhất handoff, điều phối finalize | Không gọi MCP trực tiếp |
| Entity/customer | Xác định customer/order candidate và context liên quan | `get_customer_history`; `get_order` khi Pha 3 xác nhận phù hợp |
| Order/product | Kiểm tra order, item, product và seller facts | `get_order`, `get_order_items`, `get_product_context`, `get_sellers` |
| Shipment | Phân tích trạng thái và timeline giao hàng | `get_shipment_summary` |
| Payment/refund | Đối soát capture, payment timeline và refund | `get_order_payments`, `get_payment_timeline`, `get_refund_timeline` |
| Conflict resolver | So sánh evidence đã thu thập, ghi conflict và nguồn được chọn | Không gọi MCP trực tiếp |
| Policy | Đọc policy áp dụng cho các facts đã xác thực | `get_policy` |
| Verifier | Kiểm tra consistency, schema, provenance và confidence | Không gọi MCP trực tiếp |

Least privilege là mặc định: role chỉ gọi tool trong hàng của mình, luôn truyền
đúng `case_id`, và không suy đoán tham số khi chưa có contract Gateway.

## 4. Trace và lifecycle

Các event hợp lệ đã có trong `trace-event-v1.schema.json`:

| Điểm chuyển trạng thái | Event | Actor |
| --- | --- | --- |
| Case vào hệ thống | `case_received` | coordinator |
| Giao specialist task | `task_assigned` | coordinator |
| Evidence được dùng | `tool_result_consumed` | specialist tương ứng |
| Kết quả chuyển agent | `handoff` | agent gửi |
| Policy kết luận | `policy_decided` | policy |
| Verifier chấp nhận/từ chối | `verification_completed` | verifier |
| Đóng case | `case_finalized` | coordinator |

`tool_result_consumed` phải chứa `tool_name` và `evidence_refs`. Không ghi event
cho suy luận nội bộ không quan sát được.

## 5. Timeout, retry và conflict

- MCP timeout hoặc lỗi: mặc định không retry tự động. Trả `status="blocked"`,
  `error_code="mcp_timeout"` hoặc mã lỗi tương ứng và hạ kết luận về thiếu bằng
  chứng, không bịa dữ liệu; việc retry thủ công phải do coordinator quyết định
  ở một lần chạy khác để không tăng audit/tool cost ngoài chủ ý.
- Specialist timeout hoặc kết quả sai contract: ghi lỗi theo từng call, giữ các
  findings/evidence refs hợp lệ đã nhận và tiếp tục các call độc lập còn lại
  trong task. `SpecialistResult` có thể `blocked` nhưng vẫn chứa partial
  findings; không tạo vòng handoff và không coi lỗi là evidence phủ định.
- Entity `ambiguous` hoặc `not_found`: giữ candidate bị loại trong state; không
  gọi các specialist phụ thuộc order đã unresolved và chỉ cho phép kết luận
  `needs_investigation` nếu thiếu evidence.
- Conflict: giữ cả các nguồn và `conflict_id`, không ghi đè evidence. Conflict
  resolver chọn nguồn theo policy khi đủ căn cứ; nếu chưa đủ thì để unresolved
  và verifier chặn finalize.
- Cache chỉ trong phạm vi `case_id` + tool + request đã xác nhận; không dùng
  evidence chéo case và không retry vô hạn.

## 6. Invariant trước khi finalize

Coordinator chỉ chuyển `ready_for_verification` khi:

1. mọi result có cùng `case_id`, task hợp lệ và role đúng quyền;
2. mọi `evidence_ref` là reference Gateway đã nhận, không tự sinh và không trùng
   sai phạm vi case;
3. entity resolution đã ghi order resolved/rejected rõ ràng;
4. claim, conflict và conclusion đều liên kết được với evidence hoặc được đánh
   dấu thiếu bằng chứng;
5. policy đã quyết định primary issue, responsible parties và financial
   resolution nhất quán;
6. output dự kiến không có field ngoài L3B schema, confidence nằm trong `[0, 1]`,
   và tổng tiền/refund không mâu thuẫn;
7. lifecycle trace có đủ event bắt buộc và `TraceWriter` đã validate từng event.

Verifier phải từ chối finalize nếu bất kỳ invariant nào không đạt. Chỉ sau đó
coordinator mới phát `case_finalized` và ghi output.

## 7. Pha 3 investigation flow

Input bundle L3B đã xác nhận có các field `candidate_order_ids`,
`customer_request.claimed_order_id`, `customer_unique_id_hint`,
`investigation_scope` và `policy_version`. Coordinator gọi `get_order` một lần
cho mỗi ID duy nhất trong candidates và claimed order. Chỉ một order có response
`data.order_id` khớp request mới được resolve; response mâu thuẫn được ghi
rejected, còn lỗi hoặc nhiều match giữ trạng thái ambiguous.

Sau khi resolve đúng một order, workflow gọi các nhóm theo scope/claims:

- `get_customer_history` với `customer_unique_id` khi scope yêu cầu;
- `get_policy` một lần với `policy_version` thực từ case;
- `get_order_items`, `get_product_context`, `get_sellers` khi
  `include_product_context` bật;
- `get_shipment_summary` cho claim giao hàng;
- `get_order_payments` và `get_payment_timeline` cho claim payment; thêm
  `get_refund_timeline` cho claim refund.

Mỗi call dùng required arguments từ `list_tool_definitions()`, được kiểm tra
least privilege trước khi gọi, không retry tự động và ghi evidence ref qua
`tool_result_consumed`. Các response shape đã được xác nhận trong một smoke run
trên một case: order/customer history là object, items/payments/products/sellers
là list, shipment/payment timeline là object chứa lists, policy là object chứa
`policy_version` và `rules`. `get_refund_timeline` có thể trả lỗi khi case không
có refund; workflow giữ case ở `needs_investigation`.

Pha 3 chỉ thu thập và liên kết evidence. Nó không biến policy evidence thành
primary issue, responsible party hoặc refund decision; vì vậy chưa phát
`policy_decided`. Phần còn cần xác nhận trước batch là coverage thực tế của
response shape trên toàn bộ case và các business mapping thuộc Pha 4.

## 8. Pha 4 verifier và confidence

Verifier gọi `Contracts.validate_output()` làm validator schema duy nhất, sau đó
kiểm tra các invariant xác định được từ output: confidence trong `[0, 1]`,
`insufficient_evidence` đi cùng `needs_investigation`, thiếu evidence không được
kết luận `action_required` hoặc `no_action`, refund phải khớp tổng refund lines,
`no_action` không có refund, và conflict chưa chọn nguồn phải giữ
`needs_investigation`.

Confidence chỉ được đặt về `0.0` khi state và output đều không có evidence và
case đang `needs_investigation`; nếu không có tín hiệu rõ ràng thì giữ giá trị
đang có. `policy_decided` chỉ được phát sau quyết định policy thực tế. Khi chưa
có input bundle hoặc `policy_version`, workflow không gọi `get_policy`, không
phát event này và không tạo kết luận nghiệp vụ.

## 9. Pha 4 business mapping

Sau khi entity được resolve, coordinator chỉ map output khi có đủ order/payment hoặc shipment facts, rule tương ứng từ `get_policy`, và evidence refs thực đã thu. Topic claim, `policy_version`, hoặc `requested_full_refund` tự nó không tạo ra kết luận. Event `policy_decided` chỉ được phát khi mapper đã tạo primary issue, responsible parties, action và financial resolution phù hợp rule.

Các issue được hỗ trợ khi response shapes đã biết và evidence đủ là `canceled_order_paid`, `unavailable_order_paid`, `valid_split_payment`, và shipment delay khi timeline xác định được seller/logistics. Topic không có rule, refund detail chưa xác nhận, conflict, response shape thiếu, hoặc specialist blocked ở evidence cần thiết đều giữ `needs_investigation`. Lỗi `get_refund_timeline` không được dùng để suy ra không có refund; payment evidence độc lập vẫn được giữ.

Mapper dùng `Decimal` cho tổng payment/refund và tạo refund lines khớp tổng. Verifier vẫn dùng `Contracts.validate_output()` là schema validator duy nhất, kiểm tra cùng case, provenance evidence trong state, conflict chưa giải quyết, confidence và quan hệ refund/status.

Ghi chú cập nhật: phần mapping ở mục 9 là bước Pha 4 hiện hành và thay thế giới hạn “chưa phát `policy_decided`” của mô tả Pha 3 khi rule cùng evidence đã đủ.
