# Darwin Loop

**Darwin Loop** is an autonomous optimization platform designed to evolve AI agents through a closed-loop system of telemetry, genetic mutation (GePa), and A/B testing. It empowers Product Managers (PMs) to define success via KPIs, enabling agents to self-improve their prompts and weights.

---

## 🏗 System Architecture & Module Status

| Module | Status | Description |
| :--- | :--- | :--- |
| **Telemetry (SDK)** | ✅ | Captures interaction context, token usage, latency, and custom events via `darwin-client-lib`. |
| **Privacy Scrubber** | ✅ | Automated PII anonymization and scrubbing for compliant data logging. |
| **Goal Engine** | ✅ | Validates agent performance against hard-rule KPIs (e.g., token/latency thresholds). |
| **Semantic Referee** | 🏗 | LLM-based evaluation of agent quality and goal attainment (subjective criteria). |
| **GePa (Mutation)** | 🔜 | Genetic Programming Engine for evolving prompts and system weights. |
| **Backend API** | ✅ | FastAPI server managing agent versions, experiment history, and feedback loops. |
| **Database** | ✅ | SQL persistence for agent state, version history, and interaction traces. |
| **PM Dashboard** | 🔜 | Web UI/Playground for viewing experiment results and approving mutations. |
| **Fine-tuning Pipeline**| 🔜 | Automated integration with SFT (Supervised Fine-tuning) platforms. |

---

## 🔄 The Reflective Optimization Loop

Darwin Loop operates on a continuous cycle:

1.  **Capture [✅]:** Interaction data is collected via SDK with OTel-compatible tracing.
2.  **Evaluate [✅]:** The **Goal Engine** compares agent output against defined KPIs (Hard/Soft rules).
3.  **Analyze [🏗]:** The system correlates interaction patterns with goal success/failure.
4.  **Evolve [🔜]:** The **GePa Engine** uses the feedback data to generate improved prompt mutations.
5.  **Validate [🔜]:** A/B tests compare new versions against baseline performance.
6.  **Deploy [🔜]:** Winner versions are promoted to production.

---

## 🚀 Getting Started

1. **Install SDK:** `pip install darwin-client-lib`
2. **Setup SDK:** Initialize with your agent context.
   ```python
   from darwin_client import DarwinClient
   client = DarwinClient(api_key="your_api_key")
   ```
3. **Define Goals:** Configure your performance KPIs (tokens, message count, latency) in the agent settings.
4. **Iterate:** Let the system collect trace data and generate improvement recommendations.

---

*Darwin Loop: Making your agents 1% better every iteration.*
