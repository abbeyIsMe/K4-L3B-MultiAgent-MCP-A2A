TỔNG QUAN & PHÂN BỔ THỜI GIAN (240 PHÚT)
Về bài lab này
Xây dựng hệ thống Multi-Agent điều tra tranh chấp TMĐT, trích xuất bằng chứng có thẩm quyền qua MCP Evidence Gateway và đóng gói kết quả kiểm chứng (manifest, trace, outputs) theo JSON Contract.
K4 L3A / L3B — Multi-Agent MCP + A2A
Xây dựng hệ Multi Agent điều tra case thương mại điện tử
Nên có tuân thủ theo contract và schema được định nghĩa: Repo không chứa sẵn raw dataset, đáp án hay scoring oracle. Toàn bộ input đề thi sẽ release trên Github Release, evidence được truy vấn trực tiếp qua MCP Evidence Gateway, và kết quả nộp bài được chấm tự động với hệ thống auto chấm điểm N7. Kho lưu trữ chính thức (Official Starter Repositories): - Lớp A (L3A): https://github.com/VinUni-AI20k/K4-L3A-MultiAgent-MCP-A2A - Lớp B (L3B): https://github.com/VinUni-AI20k/K4-L3B-MultiAgent-MCP-A2A Quy tắc Fork Repo: Khi Fork repo về tài khoản cá nhân hoặc nhóm, bắt buộc giữ nguyên tên gốc của repo (K4-L3A-MultiAgent-MCP-A2A hoặc K4-L3B-MultiAgent-MCP-A2A), tuyệt đối không đổi tên repo.
Registration code
Mã đăng ký cho học viên: 6NlPQJk116GaTWY5Dr6vRIGLJQz9D840KCF4P-2dVacMGPcDLhmnMYSDNWHaqD9m

Pha	Thời lượng	Trọng tâm chính	Deliverable nghiệm thu
Pha 1	00 – 30m	Đăng ký team, Fork repo, cài đặt .env, ping MCP Gateway	MCP Tool Discovery thành công qua day09 mcp-tools
Pha 2	30 – 65m	Thiết kế Multi-Agent A2A & Khung State Contract	ARCHITECTURE.md, State & Event Schema models
Pha 3	65 – 110m	Triển khai Specialist Agents & MCP Evidence Gateway	Các worker truy vấn MCP, thu thập evidence_ref
Pha 4	110 – 150m	Policy Engine, Verifier & Calibration	Nhất quán đa trường, hiệu chuẩn confidence
Pha 5	150 – 210m	Tải inputs, chạy Batch Run & Thẩm định output/trace	day09 run tạo đủ outputs/ và traces/trace.jsonl
Pha 6	210 – 240m	Đóng gói ZIP gồm (manifest.json + trace.jsonl + outputs/), nộp bài trên hệ thống	day09 package tạo submission.zip hợp lệ
PHA 1: ĐĂNG KÝ TEAM, MÔI TRƯỜNG & MCP GATEWAY PING (0 – 30 PHÚT)
Mục tiêu:
Nhằm mục đích audit quá trình của thành viên, nhóm trên hệ sinh thái thi đấu, khởi tạo môi trường Python chuẩn với CLI day09, và kết nối thông suốt với MCP Evidence Gateway.

Thao tác thực hiện:
1. Đăng ký team và nhận API KEY
1. Tất cả thành viên nhóm truy cập URL cuộc thi: https://n7-competition.pages.dev/register.
2. Điền đầy đủ thông tin:
Tên Team: Đặt theo cú pháp K4-TeamXX-<TenNhom>.
Mã học viên cá nhân & Danh sách thành viên trong nhóm, ở đây tất cả các thành viên cần đăng ký và khai báo thành viên khác trong team của mình nhé.
Mã đăng ký (Registration Code) do Lab Coach công bố tại lớp và gửi lại cho mọi người.
1. Nhận Team API Key dạng: sk-team-....
CỰC KỲ QUAN TRỌNG: Key chỉ hiển thị DUY NHẤT 01 LẦN. Hãy sao chép ngay lập tức. Tuyệt đối không gửi key qua kênh chat công khai và không commit vào Git repo, lộ ra thì ảnh hưởng kết quả cá nhân của bạn đó
2. Fork và Clone Repo chính thức
1. Đại diện nhóm truy cập link repo tương ứng với lớp của mình:
Lớp A: https://github.com/VinUni-AI20k/K4-L3A-MultiAgent-MCP-A2A
Lớp B: https://github.com/VinUni-AI20k/K4-L3B-MultiAgent-MCP-A2A
1. Nhấn nút Fork (giữ nguyên tên repo gốc).
2. Clone repo về máy:
git clone <url_repo_fork_cua_nhom>
cd K4-L3A-MultiAgent-MCP-A2A
Chép
(Hoặc cd K4-L3B-MultiAgent-MCP-A2A tùy theo lớp).

3. Khởi tạo môi trường lập trình & Cài đặt gói day09
Yêu cầu Python 3.11 trở lên:

# 1. Tạo môi trường ảo
python -m venv .venv

# 2. Kích hoạt môi trường ảo:
# Trên Windows PowerShell:
.venv\Scripts\Activate.ps1
# Trên Linux / macOS:
source .venv/bin/activate

# 3. Cài đặt package ở chế độ editable cùng dev dependencies
python -m pip install -e ".[dev]"
Chép
4. Cấu hình biến môi trường (.env)
Sao chép .env.example thành .env và điền thông tin:

cp .env.example .env
Chép
Nội dung .env:

COMPETITION_API_URL=url_competition
COMPETITION_TEAM_API_KEY=sk-team-your_key_here
MCP_ENDPOINT=http://domain/mcp
Chép
(Nếu nhóm sử dụng LLM từ các nhà cung cấp bên ngoài như OpenAI, Gemini, Claude, có thể khai báo thêm biến môi trường riêng tại đây, repo là của các bạn, tùy ý custom sao cho giải quyết được vấn đề nhanh nhất và chính xác tối đa).

5. Kiểm tra kết nối MCP Evidence Gateway
Chạy bộ kiểm tra starter và danh sách MCP tools:

pytest -q
day09 --help
day09 mcp-tools
Chép
Pass Signal Pha 1: - pytest -q pass toàn bộ unit tests starter. - day09 mcp-tools xác thực thành công qua COMPETITION_TEAM_API_KEY và in ra danh sách MCP Tools thẩm quyền (get_order, get_payment, get_shipment, get_seller, get_policy,...).



PHA 2: THIẾT KẾ MULTI-AGENT A2A & CONTRACT SCHEMAS (30 – 65 PHÚT)
Mục tiêu:
Thiết lập kiến trúc phối hợp đa tác tử (A2A), phân định trách nhiệm từng Agent và khóa cứng Schema chuẩn trong contracts/schemas/.

Kiến trúc kỳ vọng:
                          ┌──────────────────────────┐
                          │   Coordinator / Router   │
                          └─────────────┬────────────┘
                                        │ (Handoff)
         ┌──────────────────────────────┼──────────────────────────────┐
         ▼                              ▼                              ▼
┌──────────────────┐           ┌──────────────────┐           ┌──────────────────┐
│ Order/Item Agent │           │  Payment Agent   │           │  Shipment Agent  │
└────────┬─────────┘           └────────┬─────────┘           └────────┬─────────┘
         │                              │                              │
         └──────────────────────────────┼──────────────────────────────┘
                                        │ (MCP Evidence Collector)
                                        ▼
                               ┌──────────────────┐
                               │   Policy Agent   │
                               └────────┬─────────┘
                                        │
                                        ▼
                               ┌──────────────────┐
                               │  Verifier Agent  │
                               └────────┬─────────┘
                                        │ (Validated Output)
                                        ▼
                                   [END OUTPUT]
Chép
Các nhiệm vụ trọng tâm:
1. Khóa Public Contracts (contracts/schemas/):
l3a-output-v2.schema.json (hoặc l3b): Schema bắt buộc cho output từng case.
trace-event-v1.schema.json: Schema cho trace log observable.
submission-manifest-v2.schema.json: Schema cho manifest khi đóng gói nộp bài.
mcp-evidence-response-v1.schema.json: Cấu trúc phong bì (envelope) trả về từ MCP Gateway.
Nguyên tắc: Không thêm bất kỳ field nào ngoài schema. Nếu có sai lệch, JSON Schema luôn là chân lý ưu tiên tối cao, tuyệt đối tuân thủ chỗ này nhé các bạn, ràng buộc đau đớn mà liêm
1. Linh hoạt framework các bạn là kỹ sư thiết kế thực chiến nên là thoải mái sáng tạo:
Điểm triển khai chính nằm tại: src/student_agent/workflow.py:
async def solve_case(case: dict[str, Any], gateway: EvidenceGateway, trace: TraceWriter) -> dict[str, Any]:
    # Triển khai coordinator và specialist agents tại đây
    ...
Chép
Cuộc thi không chấm điểm dựa trên tên framework (học viên có thể dùng LangGraph, Semantic Kernel, CrewAI hoặc thuần Python async state-machine). Hệ thống chỉ đánh giá kết quả nghiệp vụ, tính hợp lệ của bằng chứng MCP và trace log.
1. Hoàn thiện mô tả kiến trúc trong ARCHITECTURE.md:
Phác thảo luồng handoff, tool permissions của từng agent, cơ chế retry khi MCP gặp sự cố.



PHA 3: TRIỂN KHAI SPECIALIST AGENTS & MCP GATEWAY (65 – 110 PHÚT)
Mục tiêu:
Từng agent chuyên trách truy vấn bằng chứng có thẩm quyền qua MCP Evidence Gateway theo đúng scope của từng case và ghi nhận trace audit.

Nguyên tắc của MCP Gateway:
#	Nguyên tắc	Nếu vi phạm
1	Truyền đúng case_id cho mọi MCP call	Bị từ chối truy cập (403 Forbidden)
2	KHÔNG tự sinh hoặc sửa đổi evidence_ref	Hard Gate 0 điểm toàn bài
3	Chỉ trích dẫn evidence thực sự hỗ trợ kết luận	Bị trừ điểm thành phần Evidence Relevance
4	Ghi nhận event tool_result_consumed trong trace	Không được công nhận tính xác thực
5	Server lưu Audit độc lập (Hash, Latency, Status)	Bị phát hiện nếu giả mạo trace client
Đọc kĩ chỗ này để tránh được các lỗi nhé mọi người.

Triển khai cụ thể:
1. Gọi Tool qua Gateway:
# Lấy dữ liệu đơn hàng có thẩm quyền từ MCP
evidence = await gateway.call(
    "get_order",
    case_id=case["case_id"],
    order_id=order_id,
)
evidence_ref = evidence["evidence_ref"]
order_data = evidence["data"]
Chép
1. Ghi nhận Trace Event hợp lệ:
# Ghi nhận sự kiện tiêu thụ bằng chứng vào trace audit
trace.emit(
    case_id=case["case_id"],
    event_type="tool_result_consumed",
    actor="order-agent",
    tool_name="get_order",
    evidence_refs=[evidence_ref],
)
PHA 4: POLICY ENGINE, VERIFIER & CALIBRATION (110 – 150 PHÚT)
Mục tiêu:
Áp dụng chính sách trọng tài tranh chấp, kiểm chứng chéo mâu thuẫn dữ liệu và hiệu chuẩn độ tin cậy.

Triển khai:
1. Policy Agent:
Ra quyết định dựa trên chính sách contracts/scoring/scoring-policy-v2.json:
Primary Issue: Xác định lỗi cốt lõi (canceled_order_paid, late_delivery_seller, late_delivery_logistics, payment_mismatch,...).
Responsible Party: Phân định trách nhiệm rõ ràng (seller, platform, logistics_provider, payment_provider, customer).
Financial Resolution: Số tiền hoàn chính xác (recommended_refund_brl, refund_lines).
Resolution Actions: Các hành động cụ thể cần thực hiện.
1. Verifier Agent & Confidence Calibration:
Cross-field Consistency: Đảm bảo primary_issue, responsible_parties và financial_resolution hoàn toàn logic và nhất quán (ví dụ: lỗi do người bán thì đơn vị vận chuyển không thể chịu trách nhiệm hoàn tiền).
Confidence Calibration: Đánh giá điểm tin cậy confidence [0.0 - 1.0] dựa trên chất lượng và độ đầy đủ của evidence (không tự tin thái quá 1.0 nếu bằng chứng có mâu thuẫn).
Lifecycle Events: Đảm bảo traces/trace.jsonl ghi nhận đủ các event bắt buộc:
case_received -> task_assigned -> tool_result_consumed -> handoff -> policy_decided -> verification_completed -> case_finalized.



PHA 5: TẢI INPUTS, BATCH RUN 100 CASES & XÁC THỰC (150 – 210 PHÚT)
Mục tiêu:
Tải bộ đề thi từ Github Release, chạy batch run toàn bộ cases và thẩm định tính toàn vẹn của outputs và trace log.

Quy trình thực hiện:
1. Tải và giải nén Test Bundle
1. Tải file ZIP input tương ứng (l3a-inputs-*.zip hoặc l3b-inputs-...) từ Github Release và giải nén vào thư mục inputs/ của repo, mọi người để đâu cho tiện là được không khống chế inpút :
unzip l3a-inputs-*.zip -d .
Chép
1. Cấu trúc sau khi giải nén:
case-set.json
inputs/
├── L3A_CASE_001.json
├── ...
└── L3A_CASE_100.json
Chép
1. Xác thực tính hợp lệ của tập input:
day09 validate-inputs
Chép
Pass Signal Pha 5.1: Terminal in ra thông báo hợp lệ, ví dụ: OK: l3a / v2.1 / 100 cases
2. Chạy Batch Run toàn bộ Cases
Thực thi pipeline xử lý toàn bộ cases thông qua CLI:

day09 run
Chép
Lệnh sẽ tự động lặp qua từng case trong case-set.json, gọi hàm solve_case trong workflow.py.
Tạo các tệp kết quả tại:
outputs/<case_id>.json (đủ 100 cases)
traces/trace.jsonl (toàn bộ dòng sự kiện timeline)
3. Thẩm định kết quả trước khi đóng gói
Kiểm tra tính tuân thủ Schema của toàn bộ outputs và trace:

day09 validate
Chép
Pass Signal Pha 5.2: Terminal in ra thông báo xác nhận: OK: 100 outputs / <N> trace events



PHA 6: ĐÓNG GÓI ZIP, NỘP BÀI & GITHUB (210 – 240 PHÚT)
1. Quy chuẩn cấu trúc tệp ZIP Submission Mới
Tệp submission.zip Bắt buộc chỉ chứa 3 thành phần tại thư mục gốc của ZIP (tuyệt đối không có thư mục bọc ngoài nha mọi người, hệ thống unzip ra chấm 0đ vì không đọc được vào trong):

submission.zip
├── manifest.json
├── trace.jsonl
└── outputs/
    ├── L3A_CASE_001.json
    ├── L3A_CASE_002.json
    └── ... (đủ đúng 100 files output)
Chép
Chi tiết 3 thành phần bắt buộc:
1. manifest.json: Khai báo metadata đợt thi theo chuẩn submission-manifest-v2.schema.json:
{
  "schema_version": "day09-submission-manifest-v2",
  "competition_id": "day09-multiagent-mcp-a2a",
  "variant_id": "l3a",
  "case_set_version": "v2.1",
  "output_schema_version": "day09-l3a-output-v2",
  "trace_schema_version": "day09-trace-event-v1",
  "generated_at": "2026-09-25T08:00:00Z",
  "client": {
    "name": "day09-student-starter",
    "version": "0.1.0"
  }
}
Chép
1. trace.jsonl: Toàn bộ nhật ký audit event đa tác tử, đặt ngay tại root của ZIP.
2. outputs/: Thư mục chứa đúng 100 file JSON kết quả cho từng case.
Lưu ý: - Không đưa mã nguồn src/, file .env, Team API Key, raw inputs hay debug logs vào ZIP.
2. Lệnh đóng gói tự động chuẩn hóa
Để tránh sai sót thủ công, sử dụng lệnh đóng gói tích hợp sẵn trong CLI day09:

day09 package --output dist/submission.zip
Chép
Pass Signal Pha 6: Console in ra: OK: .../dist/submission.zip Lệnh này đã tự động chạy bộ kiểm tra toàn diện: validate 100 outputs, validate trace events, build manifest V2, kiểm tra dung lượng và quét regex phát hiện leak API Key trước khi xuất file zip.
3. Nộp bài lên Competition Workspace
1. Vào trang nộp bài và upload file zip đó lên
2. Hệ thống queue vào và auto scoring, đợi kết quả
3. Mọi người dùng filter tìm nhóm mình nếu không top 10 scorer hêhe



TIÊU CHÍ CHẤM ĐIỂM & BẢNG TRỌNG SỐ
1. Bảng Trọng Số Đánh Giá
Thành phần	Ý nghĩa đánh giá	Trọng số L3A	Trọng số L3B
semantic	Độ đúng nghiệp vụ (lỗi vi phạm, trách nhiệm, số tiền hoàn)	45%	40%
evidence	Độ bao phủ và chất lượng bằng chứng trích xuất	15%	15%
provenance	Bằng chứng khớp 100% với audit trail của MCP Gateway	15%	15%
consistency	Tính nhất quán logic giữa các trường dữ liệu	10%	10%
schema	Tuân thủ 100% JSON Schema hợp lệ	5%	5%
calibration	Độ tin cậy confidence phản ánh đúng chất lượng bằng chứng	5%	5%
workflow	Quy trình phối hợp đa tác tử thể hiện trong trace.jsonl	5%	5%
efficiency	Tối ưu hóa số lượng MCP tool calls	0%	5%
Đây chỉ là tiêu chí được public, còn các hidden thì tụi mình sẽ công bố sau để đảm bảo tính công bằng

3. Cảnh Báo Hard Gates
Bài nộp sẽ nhận 0 điểm nếu vi phạm bất kỳ điều nào sau đây: 1. Sai case_id hoặc không đủ 100 cases theo danh sách case-set.json. 2. Output không thỏa mãn JSON Schema (l3a-output-v2.schema.json / l3b). 3. Thiếu bằng chứng (evidence_ref) bắt buộc cho kết luận. 4. evidence_ref không tồn tại trong hệ thống MCP Audit hoặc thuộc về team/run/case khác. 5. Cấu trúc file ZIP sai quy chuẩn (bị bọc thư mục ngoài, thiếu manifest.json hoặc trace.jsonl).







