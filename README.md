### 1. `Request` (Data Serialization & Lifecycle State Machine)
Tracks independent transaction profiles using unique session identification (`UUID4`). Encapsulates localized state transformations across four explicit milestones:
* 🔵 `Sending`: Packet initialization and dispatch.
* 🟡 `Processing`: Active queue serialization.
* 🟠 `Retrying`: Automated error-handling fallback sequence.
* 🟢 `Completed` / 🔴 `Failed`: Definitive lifecycle terminal states.

### 2. `RequestQueue` (Buffer Serialization Layer)
Manages transactional ordering using a FIFO linear structure. Features optimized method entry-points:
* `enqueue()`: Constant-time $O(1)$ append operation updating packet states to processing.
* `dequeue()`: Sequenced line extraction serving requests to available network nodes.

### 3. `Server` & `Cache` (Processing & Volatile Memory Layout)
Simulates a multi-threaded execution cluster holding two foundational pieces of operational state:
* **Fault-Injection Engine**: Implements stochastic variables to model a volatile **80% network packet drop-rate**, aggressively stress-testing framework resilience.
* **In-Memory Hashmap Storage**: A dedicated high-speed lookup cache layer. By mapping successful network resolutions as persistent keys, duplicate data queries bypass network hardware risks completely via a constant-time **$O(1)$ lookup routine**.

---

## 🏎️ Core System Mechanics

### 1. Microservice Resiliency Loop
When network hardware triggers a packet failure, the server executes an encapsulated error recovery protocol:
1. Validates the packet’s structural limits against maximum retry bounds (`max_retries`).
2. If bounds permit, increments the localized retry offset and alters transaction status to `Retrying`.
3. Re-enqueues the packet recursively back into the active `RequestQueue` execution pipeline.

### 2. Low-Latency Caching Strategy
To maximize data throughput and protect backend infrastructure from redundant traffic spikes, the server implements an exclusive lookup-on-arrival design pattern:

```diff
+ 🟩 CACHE HIT LOGIC
If Request.endpoint exists in Server.cache:
   -> Increment global Cache Hit Metrics
   -> Instantly transition Status to "Completed"
   -> Bypass network simulation entirely (Zero performance penalty)

- 🟥 CACHE MISS LOGIC
If Request.endpoint does NOT exist in Server.cache:
   -> Increment global Cache Miss Metrics
   -> Push packet to physical Network Engine
   -> On Network Success: Populate Server.cache[endpoint] = 1