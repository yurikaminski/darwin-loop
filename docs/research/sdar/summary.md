Self-Distilled Agentic Reinforcement Learning
Zhengxi Lu1,2∗, Zhiyuan Yao 1,2, Zhuowen Han2, Zi-Han Wang2,3, Jinyang Wu3
Qi Gu2†,Xunliang Cai 2,Weiming Lu 1,Jun Xiao 1,Yueting Zhuang 1,Yongliang Shen 1†
1Zhejiang University 2Meituan 3Tsinghua University
{zhengxilu, syl}@zju.edu.cn guqi03@meituan.com
Abstract
Reinforcement learning (RL) has emerged as a central paradigm for post-
training LLM agents, yet its trajectory-level reward signal provides only
coarse supervision for long-horizon interaction. On-Policy Self-Distillation
(OPSD) complements RL by introducing dense token-level guidance from a
teacher branch augmented with privileged context. However, transferring
OPSD to multi-turn agents proves problematic: compounding multi-turn
instability destabilizes supervision, while skill-conditioned privileged guid-
ance requires asymmetric treatment for negative teacher rejections may
arise from imperfect skills retrieval or utilization. We introduceSDAR
(Self-DistilledAgenticReinforcement Learning), which treats OPSD as a
gated auxiliary objective while keeping RL as the primary optimization
backbone. SDAR maps detached token-level signals into a sigmoid gate,
strengthening distillation on teacher-endorsed positive-gap tokens and
softly attenuating negative teacher rejections. Across the Qwen2.5 and
Qwen3 families on ALFWorld, WebShop, and Search-QA, SDAR substan-
tially improves over GRPO (+9.4% on ALFWorld, +7.0% on Search-QA,
+10.2% on WebShop-Acc), avoids the instability of naive GRPO+OPSD, and
consistently outperforms hybrid RL–OPSD baselines across model scales.
Code available:https://github.com/ZJU-REAL/SDAR.
Figure 1: (a) Comparison between GRPO+OPSD and SDAR; (b) Overall Performance.
∗Work done during internship at Meituan.
†Corresponding author
1
arXiv:2605.15155v1  [cs.LG]  14 May 2026
1 Introduction
Agentic post-training has become a central challenge for Large Language Models
(LLMs) (Guo et al., 2025; Team et al., 2025; Yang et al., 2025; Comanici et al., 2025; Team et al.,
2026b). Unlike static single-turn reasoning, multi-turn agents interact with environments
over extended horizons, where each action changes future observations and each generated
response becomes part of the context for subsequent decisions (Shen et al., 2023; Shi et al.,
2025; Jimenez et al., 2023).
Two paradigms naturally emerge as complementary forces: Reinforcement Learning
(RL) (Shao et al., 2024; Dong et al., 2025; Feng et al., 2025) provides task-level optimization
grounded in environment or verifier feedback, whereas On-Policy Distillation (OPD) (Ye
et al., 2026; Yang et al., 2026b; Team et al., 2026a; GLM-5-Team et al., 2026) and On-Policy
Self-Distillation (OPSD) (Zhao et al., 2026; He et al., 2026; Zhang et al., 2026) provide dense
token-level guidance from a teacher branch. Yet, OPSD does not transfer cleanly to multi-
turn agent training. We attribute this to two observations:[1] Multi-turn OPSD Instability
and[2] Asymmetric Trust in Privileged Guidance.
[Observation-1] Multi-turn OPSD InstabilityOnce the student agent inevitably drifts
0 50 100 150
Training Steps
0.00
0.05
0.10
0.15
0.20
0.25
0.30
0.35KL Loss
GRPO+OPSD
GRPO
RLSD
0 5 10 15 20
Turn Step
1.0
1.5
2.0
2.5
3.0KL Divergence
Multi-turn OPSD
Training Steps
0.1
0.2
0.3Success Rate
Multi-turn OPSD
Figure 2:Left: Multi-turn OPSD Instability, with performance
and KL reported.Right: RLSD-Style Instability, with KL loss.
from the teacher-supported tra-
jectory, the once-helpful token-
level supervision becomes increas-
ingly unreliable. This compound-
ing error leads to surging per-
turn KL divergence and catas-
trophic degradation in task per-
formance, as shown in Figure 2
(Left). TCOD (Wang et al., 2026b)
attempts to address this through
curriculum learning, but relies
on rigid temporal schedules or
trajectory-depth thresholds.
[Observation-2] Asymmetric Trust in Privileged Guidance.In OPSD, the teacher branch
is not an independently stronger model, but the same policy augmented with privileged
training-only context, such as retrieved skills. This makes its token-level guidance inherently
asymmetric. For a student-sampled token yt, if the privileged teacher assigns a higher
probability than the student, the retrieved skill provides an endorsement signal: it supports
an on-policy behavior that the student can already generate but has not fully internalized.
Such positive guidance is particularly suitable for distillation.
In contrast, if the privileged teacher assigns a lower probability to the sampled token, the
signal should be interpreted more cautiously. A negative gap may indicate that the token
should indeed be suppressed, but in skill-conditioned OPSD it may also arise from the insta-
bility of privileged context:(1) Skill Quality.Retrieved skills may be irrelevant, incomplete,
or redundant.(2) Skill Utilization.The teacher may fail to ground even relevant skills
into reliable token-level preferences (Chen et al., 2019).(3) Multi-turn Drift.As trajectories
unfold, the teacher-student gap tends to widen across turns (Figure 3, Middle), amplifying
early mismatches over successive decisions (Ross et al., 2011). Our preliminary study on
Qwen2.5-3B-Instruct shows that negative-gap tokens exceed 50% of all tokens (Figure 3),
making this issue pervasive. This motivates an asymmetric treatment of privileged guid-
ance: trust positive teacher endorsements more strongly, while applying negative teacher
rejections more conservatively.
A stark realization emerges: for multi-turn agents, RL could reign as the primary optimiza-
tion backbone, while OPSD is relegated to a carefully controlled auxiliary role.
But how should this auxiliary role be controlled? RLSD (Yang et al., 2026a) directly uses self-
divergence to re-weight token-level RL advantages, but can substantially amplify updates
especially early in training when teacher-student mismatch is large (see Figure 2, Right).
2
-1 -0.5 0 0.5 1
Teacher-Student Gap
0
50000
100000
150000
200000
250000Token Count
Mean=-0.1168
1 11 21 31 41
Turn Step Interval
0.11
0.12
0.13
Average Gaps
5% 30% 55% 80%
Relative Position in Turn
0.18
0.16
0.14
0.12
0.10
0.08
0.06
0.04
Average Gaps
Figure 3:Teacher-Student Gap Analysis. Left: Token count distribution partitioned by
Teacher-Student gap value.Middle: Average teacher-student gap indexed by multi-turn
step.Right: Average teacher-student gap indexed by relative position within a single turn.
We take a different path: the OPSD loss is treated as a direct, auxiliary optimization objective,
leaving the verifier-driven RL policy loss untouched and thereby strictly preserving the
semantics and unbiasedness of the RL advantage. To overcome instability of multi-turn
OPSD and privileged guidance, distillation is not performed uniformly on every token.
Instead, tokens are selectively distilled via an adaptive, smooth gating mechanism rather
than a hand-crafted, rigid schedule (such as Skill-SD (Wang et al., 2026a) and HDPO (Ding,
2026)). Inspired by TIP (Xu et al., 2026), we use token-level signals (such as student entropy
or teacher-student divergence) to control the gate’s activation. The core philosophy is
simple:let each token decide the intensity of its own supervision.This yields a dynamic, self-
paced curriculum operating at the finest possible granularity: the individual token level.
We validated our method across the Qwen2.5 and Qwen3 model families on three diverse
benchmarks for llm-based agents: ALFWorld (Shridhar et al., 2020), WebShop (Yao et al.,
2022), and Search-QA (Jin et al., 2025). SDAR achieves substantial improvements over
GRPO ( +9.4% on ALFWorld, +7.0% on Search-QA, and +10.2% on WebShop-Acc for
7B), entirely avoids the catastrophic instability of na ¨ıve GRPO+OPSD, and consistently
outperforms RL–OPSD hybrid methods such as Skill-SD and RLSD across all three model
scales (Qwen3-1.7B included). Furthermore, robustness analysis shows that SDAR degrades
gracefully with retrieval quality: even random retrieval outperforms the GRPO baseline, as
our gating design filters out noise from low-quality skills and distills beneficial signals only.
2 Method
2.1 Problem Setup
We consider a multi-turn agent that interacts with an environment over a finite horizon.
Given an initial prompt or task description x, at turn k the agent receives an observation
ok, generates a response ak, and the environment returns the next observation ok+1. Each
response ak may contain both intermediate reasoning tokens and executable action tokens.
For notational simplicity, we flatten all valid response tokens in one trajectory into a single
token sequence
y= (y1, . . . ,yT)∼π θ(· |x),
where πθ denotes the student policy and T is the total number of valid response tokens. At
token positiont, we denote the self-student context by
st = (x,y<t),
and the self-teacher context by
s+
t = (x,c+,y <t),
where c+ denotes privileged training-only context available only to the teacher branch, such
as reference answers, skills (ours), or other auxiliary information not accessible at test time.
3
Environment
Turn 1
Turn N
r1
r2
rG
τ1
τ2
τG
A1
A2
AG
Skills
Retrieval
 Self-Teacher
Gaps
Rollout
OPSD Agent Loop GRPO
Self-Student
Given the Current Situation , it seems
the sid etable 1 is empty
-0.25 0.06 -0.07 0.02 0 0.46 -0.43
0.20 -1.7 0.00 0.0 -0.03 0.28
Token-Level Gating
 Token-Level Advantages
Tokens λ* OPSD Loss + GRPO Loss
Task-Outcome Signal
Agent
Env
Action
Observation
Traj Reward
Figure 4:Illustrations of SDAR framework,which trains multi-turn agents using token-
level OPSD loss and verifier-driven RL loss.
Skills RetrievalWe retrieve task-relevantskills—compact, structured demonstrations that
encode domain-specific knowledge such as sub-goal decompositions or action templates.
We implement four retrieval strategies of varying quality to evaluate the robustness of our
framework to the fidelity of the retrieved context:(1) UCB Retrieval,(2) Keyword Matching
(KM),(3) Full Retrieval, and(4) Random Retrieval.

