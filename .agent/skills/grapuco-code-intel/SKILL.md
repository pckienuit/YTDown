---
name: grapuco-code-intel
description: >
  Khai thác Grapuco MCP để phân tích codebase, kiểm tra blast radius, trace data flow,
  debug bug, lên kế hoạch refactor, và rename symbol an toàn. Sử dụng trước khi sửa code.
triggers:
  - grapuco
  - code intel
  - blast radius
  - trace request
  - rename symbol
  - pre-commit check
  - explore codebase
  - before edit
  - impact analysis
  - investigate bug
tools:
  - mcp_grapuco_bootstrap
  - mcp_grapuco_list_repositories
  - mcp_grapuco_search_code
  - mcp_grapuco_semantic_search
  - mcp_grapuco_get_symbol_context
  - mcp_grapuco_blast_radius
  - mcp_grapuco_detect_changes
  - mcp_grapuco_rename_symbol
  - mcp_grapuco_get_data_flows
  - mcp_grapuco_get_dependencies
  - mcp_grapuco_get_architecture
  - mcp_grapuco_get_context
  - mcp_grapuco_grapuco_help
schemaVersion: 1
---

# Grapuco Code Intelligence Skill

> **MCP Server:** `grapuco` — Graph-based code analysis engine.
> Grapuco index-hóa toàn bộ codebase thành một knowledge graph (nodes = symbols, edges = CALLS/IMPORTS/EXTENDS). Tất cả tools đều CHEAP trừ `get_context` (5 AI credits).

---

## Tool Catalog

| Tool | Chi phí | Dùng khi nào |
|------|---------|--------------|
| `bootstrap` | cheap | Session đầu tiên — lấy repos + tool catalog |
| `list_repositories` | cheap | Chưa biết repo ID |
| `search_code` | cheap | Tìm symbol theo tên |
| `semantic_search` | cheap | Tìm bằng ngôn ngữ tự nhiên |
| `get_symbol_context` | cheap | 360° view của một symbol |
| `blast_radius` | cheap | Kiểm tra impact trước khi sửa |
| `detect_changes` | cheap | Phân tích git diff |
| `rename_symbol` | cheap | Đổi tên an toàn multi-file |
| `get_data_flows` | cheap | API→Service→DB traces |
| `get_dependencies` | cheap | CALLS/IMPORTS/EXTENDS graph |
| `get_architecture` | cheap | Full code map của repo |
| `get_context` | **⚠️ 5 credits** | RAG — giải thích feature/flow phức tạp |
| `grapuco_help` | cheap | Hỏi tool nào nên dùng |

---

## Scenario Playbooks

### 🔍 1. Explore Codebase (Onboard repo mới)

**Trigger:** "Codebase này làm gì?", "Giải thích kiến trúc", "Tìm entry point"

```
Step 1: bootstrap                          → Lấy repos + tool map
Step 2: list_repositories                  → Lấy repo ID chính xác
Step 3: get_architecture { repositoryId }  → Scan nodes/edges (class, routes, DB)
Step 4: search_code { "main" | "Controller" | "router" }
Step 5: get_symbol_context { nodeId }      → Focus vào entry point
Step 6: get_data_flows { repositoryId }    → Xem API→Service→DB chains
Step 7: semantic_search (nếu cần sâu hơn) → Tìm feature cụ thể
```

**⚠️ TRÁNH:** Gọi `get_architecture` trên repo rất lớn trước — bắt đầu bằng `search_code`.

---

### 🛡️ 2. Safe Edit (Kiểm tra impact trước khi sửa)

**Trigger:** "Sửa X có ảnh hưởng gì không?", "before edit", "refactor safety"

```
Step 1: search_code { "TargetSymbol" }         → Lấy nodeId chính xác
Step 2: get_symbol_context { nodeId }           → Xem callers, callees, processes
Step 3: blast_radius { target, direction:"both" }
        → Đọc: riskLevel, byDepth[0] (immediate), affectedRoutes, affectedProcesses
Step 4: (Nếu riskLevel HIGH/CRITICAL)
        → get_data_flows để xem flows bị ảnh hưởng
```

**Quyết định dựa trên riskLevel:**
| Risk | Hành động |
|------|-----------|
| LOW | Sửa tự tin |
| MEDIUM | Viết tests cho depth-1 callers |
| HIGH | Phân chia thành incremental PRs |
| CRITICAL | Cần code review + test toàn bộ affectedRoutes |

---

### 🐛 3. Investigate Bug (Debug từ stack trace)

**Trigger:** "Bug", "exception", "crash", "stack trace"

```
Step 1: search_code { "failingFunctionName" }  → Lấy nodeId
Step 2: get_symbol_context { nodeId }           → Xem callers (source?) + callees (downstream?)
Step 3: (Walk up stack) get_symbol_context cho từng frame
Step 4: blast_radius { target, direction:"upstream" }
        → Tìm tất cả paths dẫn đến lỗi
Step 5: get_dependencies { nodeId }             → Kiểm tra IMPORTS mismatch
Step 6: blast_radius { rootCause, direction:"downstream" }
        → Đảm bảo fix không phá thứ khác
```

**Nguyên tắc:** Dòng lỗi là TRIỆU CHỨNG — nguyên nhân thường ở callers (depth 1).

---

### 🔄 4. Plan Refactor (Lên kế hoạch tái cấu trúc)

**Trigger:** "Refactor X", "tách module", "split service", "extract class"

```
Step 1: blast_radius { target, direction:"both", maxDepth:3 }
Step 2: get_symbol_context { name }       → callers, routes, DB access
Step 3: Group byDepth[*].symbols theo file path:
        src/auth/  → 5 symbols
        src/user/  → 3 symbols
        → Mỗi nhóm = một work package
Step 4: Xác định cut points (interface, ít callers, low coupling)
Step 5: Lên thứ tự: Leaf changes → Interfaces → Internal → Consumer migration
Step 6: (Sau mỗi bước) detect_changes { diff } → Verify riskLevel
```

---

### 📋 5. Pre-Commit Check (Kiểm tra trước khi commit)

**Trigger:** "trước khi commit", "review changes", "git diff check"

```
Step 1: Chạy terminal: git diff HEAD
Step 2: detect_changes { diff: "<paste output>" }
Step 3: Đọc kết quả:
        - changedSymbols: symbols được sửa trực tiếp
        - impactedSymbols: symbols bị ảnh hưởng gián tiếp
        - affectedRoutes: API endpoints bị tác động
        - riskLevel: mức độ nguy hiểm tổng thể
```

**Nếu confidence < 0.8** → mapping không chắc, verify thủ công.

---

### ✏️ 6. Rename Symbol (Đổi tên an toàn)

**Trigger:** "rename", "đổi tên function/class/method"

```
Step 1: search_code { "OldName" }             → Lấy nodeId chính xác
Step 2: get_symbol_context { nodeId }         → Hiểu độ rộng trước khi rename
Step 3: rename_symbol { symbolId, newName, dryRun: true }
        → Đọc: graphEdits, textualCandidates, conflicts, summary
Step 4: Nếu hasConflicts → Giải quyết collision trước
Step 5: rename_symbol { symbolId, newName, dryRun: false }  ← CHỈ KHI ĐÃ REVIEW
```

**QUAN TRỌNG:** `textualCandidates` (strings/comments) cần review thủ công.

---

### 🌐 7. Trace Request (Theo dõi request từ API đến DB)

**Trigger:** "POST /users hoạt động thế nào?", "trace flow", "route to DB"

```
Step 1: search_code { "ControllerName" }       → Tìm handler
        OR semantic_search { "POST /users" }
Step 2: get_data_flows { httpPath: "/users" }  → Full API→Service→DB chain
Step 3: get_symbol_context cho từng layer:
        Controller → Service → Repository
Step 4: get_dependencies { nodeId }            → CALLS/IMPORTS/EXTENDS
Step 5: Build chain: Route → Controller → Service → Repo → DB
```

**Chú ý:** Kiểm tra event emissions — flow có thể phân nhánh async.

---

## Quy tắc sử dụng

### ✅ DO
- Luôn **bootstrap** ở đầu session mới để biết repos có sẵn
- Dùng **nodeId** thay vì `name` khi đã biết (tránh ambiguous)
- Gọi **blast_radius TRƯỚC** khi sửa bất kỳ function/class nào
- Nhóm `byDepth[*].symbols` theo file để tổ chức incremental work

### ❌ DON'T
- Không skip blast radius với lý do "đây là thay đổi nhỏ"
- Không bỏ qua `affectedRoutes` — đây là user-facing impact
- Không dùng `get_context` (5 credits) nếu `semantic_search` (free) đủ
- Không assume node IDs — luôn discover qua `search_code` trước

### 💡 Tips
- `get_symbol_context.callers` = ai gọi symbol này → nguồn gốc bug
- `get_symbol_context.callees` = nó gọi gì → downstream failure
- `blast_radius.byDepth[0]` = immediate dependents — vỡ trước tiên
- `riskLevel: CRITICAL` = ≥20 direct dependents HOẶC ≥3 routes bị ảnh hưởng
