# EchoSphere 2026: choosing an interview product worth building

Research date: 5 September 2026. Prepared for a student team with voice AI, ML, engineering and design experience. Build assumption: about three days, as you specified. Product names below are working names, without trademark checks.

## 1. My recommendation

Build **Relay**, a hiring interview for technical support engineers. A candidate talks to an AI customer, investigates a broken integration in a working API sandbox, and hands the case to an AI technical interviewer. The system reruns the candidate's diagnostic steps to establish whether another engineer could reproduce the problem. A hiring manager then questions the candidate about the evidence, customer commitments and remaining uncertainty.

The core problem is specific: **hiring teams need to know whether a candidate can turn a confused customer conversation into an accurate, usable engineering handoff.**

The memorable demo moment is equally specific. An API returns HTTP 200, but the customer receives duplicate fulfilment jobs. The candidate initially says the integration works. The customer challenges that conclusion. The candidate investigates, corrects the claim and produces a reproducible escalation. The final assessment points to what the candidate said, what they tested and what they changed their mind about.

I prefer this to a general interview product because you can demonstrate the value in one small case. Voice carries information the candidate must discover. The workspace supplies evidence they must interpret. The panel tests whether their explanation survives a change of audience. The handoff produces something that can be checked outside the conversation.

This is a focused hiring exercise. Practice and onboarding could become later uses. They should not be the opening pitch.

There are two serious alternatives:

| Direction | The question it answers | My judgment |
|---|---|---|
| Relay | Can this support engineer investigate a customer problem and leave a handoff another engineer can use? | Best balance of a real hiring need, essential voice interaction and a visible three-day demo. |
| ProofRound | What does this applicant actually demonstrate in a first-round recruitment interview, and what should the human interviewer investigate next? | The explicit AI recruitment interview option. Useful, but the competitive pressure is highest. |
| MetricRoom | Can this analyst defend a recommendation when stakeholders question the metric and the underlying data? | Strongest alternative if your team prefers data reasoning to support workflows. |

The uncomfortable finding is that none of the broad categories is empty. Sova already markets coordinated AI workplace simulations. Support Lab AI already combines support scenarios, API debugging and hiring assessments. Relay therefore needs its reproducible handoff to be central. A generic support simulator would be too close to existing products. [Sova Immerse](https://www.sovaassessment.com/immerse), [Support Lab AI](https://www.supportlab.ai/).

My confidence is high that the obvious interview features are crowded, moderate that Relay is a good hackathon choice, and low that customers will pay for this exact product before you interview actual buyers. The research supports a direction to test. It does not establish a business.

## 2. What the event rules change

The official event requires Agora Conversational AI as the primary real-time voice layer. Its FAQ calls for external tools or APIs and a meaningful action. It lists live evaluation, a working prototype, repository, README, architecture diagram, a 3-5 minute video, technology list and known limitations among the submission requirements. A voice-enabled chatbot or an entirely prerecorded demo can be disqualified. [Commudle event overview and FAQ](https://www.commudle.com/communities/knotic/hackathons/echosphere).

There is a timing conflict to resolve with your existing organizer guidance. The page lists September 4 at 11:59 PM IST as the deadline, September 5-6 as evaluation with no modifications, and September 12 as the finale. You said you have about three days, so the build plan uses that assumption. It does not establish permission to change an already submitted core solution.

Stay visibly within the Coordinated AI Interview Panel track. The event also has a separate incident commander track. An operational incident assistant would blur your submission's purpose. In Relay, the human is a candidate, the AI roles are interview participants, and the outcome is an assessment. [Official tracks](https://www.commudle.com/communities/knotic/hackathons/echosphere/tracks).

## 3. What already exists

These are publicly documented capabilities, generally described by the vendors themselves. I did not create product accounts or conduct hands-on trials. A product page establishes that someone markets a capability; it does not establish how reliably it works.

| Category | Products and public evidence | What this means for your project |
|---|---|---|
| Automated recruitment interviews | Alex, formerly Apriora, advertises conversational first-round interviews, adaptive follow-ups, transcripts and scores. [Alex AI interviewer](https://www.alex.com/product/ai-interviewer). | Resume questions, follow-ups and a recruiter report are established product features. |
| Connected recruitment screening | BrightHire Screen supports configurable questions, follow-up logic, scoring and connections to the employer's hiring workflow. [BrightHire Screen](https://brighthire.com/ai-interviewer/). | Adding an applicant tracking system will not make a generic interviewer distinctive. |
| Large assessment platforms entering voice interviews | CodeSignal offers live AI interviewers and configurable assessments. [CodeSignal AI Interviewer](https://codesignal.com/ai-interviewer/), [assessment setup documentation](https://support.codesignal.com/hc/en-us/articles/38064243608855-Create-an-AI-Interviewer-Assessment). | Established assessment companies already compete on the core experience. |
| Talent platforms with AI interviews | Mercor documents role-specific AI interviews and transcript-based evaluation. micro1's Zara paper describes conversational assessment and personalized feedback. [Mercor candidate documentation](https://mercor-external.mintlify.app/support/ai-interview), [Zara paper](https://arxiv.org/abs/2507.02869). | A friendly recruiter personality and feedback are insufficient product claims. |
| Explainable text interviews | Sapia offers structured chat interviews and explanations grounded in candidate responses. [Sapia science](https://sapia.ai/science/). | Evidence-based scoring is also an existing category claim. Voice must improve the task itself. |
| Recruiting administration | Paradox's Olivia supports conversational candidate interactions through the hiring journey. [Paradox candidate experience](https://www.paradox.ai/solutions/candidates). | Scheduling and application handling solve real problems, but would expand your scope into a crowded workflow. |
| Mock interviews and answer assistance | Final Round AI offers mock interviews and a separate live answer-assistance product. [Final Round AI](https://www.finalroundai.com/), [practice documentation](https://docs.finalroundai.com/docs/mock-interviews/starting-a-mock). | General practice competes for candidate attention. Prepared or assisted answers also make pure verbal fluency a weak basis for assessing work. |
| Voice interviews with whiteboards | Interview Trix combines Excalidraw, voice and rubric feedback. Archqo watches diagrams and asks follow-ups. [Interview Trix](https://www.interviewtrix.com/ai-system-design), [Archqo](https://www.archqo.com/). | A whiteboard integration is useful, but already familiar. |
| Voice, diagrams and graphs | SystemDesign.so advertises voice interruption, a drawing canvas, adaptive follow-ups and a knowledge graph. VoiceDraw builds diagrams from speech. [SystemDesign.so](https://systemdesign.so/), [VoiceDraw](https://voicedraw.com/). | Even the combination of speech and a graph needs a more specific purpose. |
| Open-source interview implementations | Loadout combines voice interviewing and Excalidraw. A separate LangGraph interview assistant documents real-time voice and shared conversational history. [Loadout](https://github.com/VC444/loadout), [LangGraph interview assistant](https://github.com/ycos-a/ai-interview). | Basic implementation patterns are easy for other teams to find. |
| Coding interviews and AI-assisted work | HackerRank offers live technical interviews with AI assistance and AI mock interviews. Karat markets expert-led interviews and AI-related simulations. [HackerRank Interview](https://www.hackerrank.com/products/interview), [HackerRank mock interviews](https://help.hackerrank.com/articles/8988753946-introduction-to-mock-interview), [Karat](https://karat.com/). | Allowing candidates to use AI or an editor is becoming part of established assessment products. |
| Code review assessments | Woven evaluates candidates reviewing AI-generated pull requests. Merge has an AI agent revise code in response to candidate review comments. [Woven code review](https://www.woventeams.com/gen-ai-code-review/), [Merge](https://mergeoa.com/). | I would not pitch "review AI-generated code" as an unexplored idea. |
| Work samples and realistic assessment | Canditech markets job simulations. HireVue offers Virtual Job Tryout. [Canditech](https://www.canditech.io/), [HireVue](https://www.hirevue.com/platform/assessment-software/virtual-job-tryout). | "Test the actual job" is a good principle with substantial prior competition. |
| Coordinated AI workplace characters | Sova Immerse has a manager briefing, conversations with simulated colleagues or customers, and a manager debrief. [Sova Immerse](https://www.sovaassessment.com/immerse). | Multiple roles sharing a continuous scenario are already being sold. |
| Technical support simulations | Support Lab AI advertises API debugging, customer scenarios, escalation assessment and pre-hire reports. [Support Lab AI](https://www.supportlab.ai/). | This is Relay's closest competitor. Hiding it would weaken the recommendation. |
| Customer service assessment | Vervoe introduced a support-center simulation involving a ticket queue and customer responses in 2021. [Vervoe launch article](https://vervoe.com/introducing-customer-service-simulator/). | A fake CRM with angry customers is an old assessment format. |
| Production reasoning assessments | ProdSimulator markets engineering screens built around production problems and simulated team discussion. [ProdSimulator](https://prodsimulator.com/). | A generic incident interview has competitors and overlaps another EchoSphere track. |
| Communication and enterprise training | Yoodli supports multiple personas, including interview panels. Second Nature offers multi-persona roleplay. Mursion provides AI and human-led simulations. [Yoodli configuration](https://support.yoodli.ai/en/articles/11565137-how-to-build-and-customize-roleplays), [Second Nature](https://secondnature.ai/), [Mursion simulations](https://www.mursion.com/platform/simulations/). | Personas, objections and realistic conversation are already central to enterprise training products. |
| Oral defense of submitted work | Rocketproof and Tolus describe AI oral exams grounded in submitted work. [Rocketproof](https://rocketproof.ai/), [Tolus](https://www.tolus.dev/oral-defense-ai). | "Explain your own assignment or project" has clear adjacent competition. |

The broad market weakness is not a total absence of features. It is the difficulty of establishing what an answer actually proves, making the exercise relevant to a particular job, and giving the human reviewer enough trustworthy evidence to act.

## 4. What other hackathon teams already build

Recent public projects make the duplication risk concrete.

**Interviewed**, submitted to the Amazon Nova AI Hackathon, describes a three-person panel with distinct voices, resume-based questions, a Monaco editor, interruption handling and recruiter reports. This is close to the obvious implementation of your statement. Its write-up also describes difficulty with panel handoffs and interrupted transcript fragments. Treat the capabilities as a team's published account, not an independently verified benchmark. [Interviewed on Devpost](https://devpost.com/software/interviewed).

**Talkode**, submitted to the UC Berkeley AI Hackathon 2026, describes voice interviews around realistic codebases, debugging, technical communication and transcript-linked evaluation. Even "interview candidates while they do real engineering work" is already a student project direction. [Talkode on Devpost](https://devpost.com/software/talkode).

**PRESSURE**, submitted to HackHive 2026, describes adaptive interview practice and a downloadable report. **MockCode** describes technical interview practice for students. Neither establishes commercial success; both show how naturally teams converge on this category. [PRESSURE](https://devpost.com/software/pressure-g97h4q), [MockCode](https://devpost.com/software/mockcode).

Agora itself appeared in earlier interview projects. Mr. Agor used Agora audio and video for remote AI interviews years before this event. [Mr. Agor on Devpost](https://devpost.com/software/mr-agor-world-s-first-rte-powered-virtual-interviewer).

I could not inspect the current EchoSphere submission inventory. Its projects page timed out twice. Any estimate of how many current teams will duplicate a direction would therefore be invented. The comparison below uses relative risk, based on how obvious the direction is and how much public precedent exists.

## 5. Why the obvious ideas are weak

| Proposed selling point | Why it is weak on its own | What would make it useful |
|---|---|---|
| Three AI interviewers with different personalities | The statement practically asks every team to build it. Existing roleplay platforms do it too. | Each role must examine a different consequence of the same decision. |
| Questions generated from the resume | Common recruitment functionality. It can produce specific-sounding questions without establishing competence. | Connect a job criterion to an observable work sample and preserve what remains unknown. |
| A difficulty slider | Easy to demonstrate, difficult to interpret fairly. | Adapt the next probe while preserving a common core task and recording assistance. |
| A transcript and numerical score | Widely available. A precise number can conceal uncertain reasoning. | Give exact evidence, a clear rubric and an explicit "not observed" state. |
| A knowledge graph | A different view of a transcript can still leave the reviewer with the same uncertainty. | Use a relationship to choose a consequential next question or check a claim against a tool result. |
| Excalidraw plus voice | Several products already combine them. | Let the candidate manipulate a representation necessary to solve the job task. |
| An ATS or calendar integration | Moves information around, but does not improve the assessment by itself. | Add it once a buyer wants to insert an already useful exercise into hiring. |
| Emotion, confidence or deception scores | Attractive demo graphics with serious validity and accessibility problems. | Assess observable job behavior. Ask for clarification when evidence is uncertain. |
| A full coding environment | Established assessment platforms have one. It also creates execution and security work. | Use only the small executable task needed to test your chosen skill. |

A general mock interview can be useful. It is weak for this particular competition because judges can understand the whole product before your demo starts. Your extra feature then has to fight for attention against better-funded products and other teams with the same starting point.

The strongest opportunity is to make a candidate's statement testable. "I resolved it" should lead to a check of the relevant outcome. "I would escalate" should lead to an actual handoff. "Revenue improved" should lead to the calculation and its assumptions.

## 6. What remains hard, and what the research actually supports

### Collecting evidence is different from proving hiring quality

The US Office of Personnel Management describes work samples as tasks resembling the actual job. It also cautions that they fit situations where applicants are expected to have the tested skills on entry. A specialized debugging exercise can unfairly test prior exposure if the employer normally teaches that knowledge after hiring. [OPM work samples and simulations](https://www.opm.gov/policy-data-oversight/assessment-and-selection/other-assessment-methods/work-samples-and-simulations/).

For Relay, provide the toy product documentation and a short unscored familiarization step. Test investigation and handoff skills. Do not quietly make knowledge of your invented API the hiring criterion.

There is credible positive evidence for AI interviewing. A July 2026 research paper reports a field experiment involving 70,884 applications for entry-level customer service jobs in the Philippines. Human recruiters retained hiring decisions. The researchers found benefits from more consistent information collection. This supports studying AI as an interviewer, but it does not validate autonomous hiring scores or establish that a student-built technical assessment predicts job performance. [Jabarian and Henkel, Voice AI in Firms](https://arxiv.org/html/2607.28222v1).

A smaller 2025 qualitative study with 20 participants found that AI technical interview practice could feel useful and improve reported confidence, while conversational timing remained a problem. Confidence after practice is a different outcome from successful hiring. [Gomez and colleagues, Virtual Interviewers, Real Results](https://arxiv.org/html/2506.16542v2).

### Adaptation can damage comparability

OPM's structured interview guidance emphasizes common questions and rating standards. Your statement requires adaptation. That creates a real design tension. [OPM structured interviews](https://www.opm.gov/policy-data-oversight/assessment-and-selection/structured-interviews).

Keep the core case and required competencies constant. Adapt clarification, depth and optional follow-ups. Record every hint. A candidate who succeeds after a hint should not appear indistinguishable from a candidate who succeeded independently. Do not rank candidates using raw scores from unequal branches.

### Changing one's mind can be good reasoning

An early hypothesis and a later corrected conclusion are not automatically contradictory. A candidate might be talking about a different time period, customer or subsystem. Transcription can also change a technical term or number.

Store the statement, its scope, when it was said and the evidence available at that time. Before criticizing inconsistency, ask the candidate to reconcile the two statements. Give credit for a justified correction. An interviewer that punishes revision teaches candidates to defend mistakes.

### Candidate trust is part of the product

Greenhouse's 2026 research describes a survey of 2,950 jobseekers across five countries. Its report identifies unclear AI use, lack of human contact and lack of follow-up as sources of dissatisfaction. This is vendor research based on self-report, not a representative estimate for Indian students. It still gives concrete design questions worth testing. [Greenhouse candidate AI interview report](https://www.greenhouse.com/uk/blog/2026-candidate-ai-interview-report).

Public discussions are mixed. Some candidates describe premature interruptions and repeated questioning; others describe clear, comfortable interviews. These are anecdotes, with unknown selection effects and possible promotional participation. They justify testing pauses, corrections and recovery, not declaring all AI interviews good or bad. [Discussion of interruption problems](https://www.reddit.com/r/micro1_ai/comments/1s85pk1/ai_interviews/), [a positive September 2026 candidate account](https://www.reddit.com/r/micro1_ai/comments/1w5361q/micro1_qa_automation_interview_experience_zara_ai/).

### A useful graph needs a decision to support

Graphologue turns model responses into interactive diagrams. MeetMap explores live dialogue maps, including versions that people can edit. Their studies concern understanding and organizing conversation, not validating hiring decisions. [Graphologue](https://arxiv.org/abs/2305.11473), [MeetMap](https://arxiv.org/abs/2502.01564).

For your product, a graph is worth keeping only if it answers a question such as "Which unresolved customer commitment depends on this untested assumption?" A graph that merely connects every utterance by topic will consume screen space and development time.

## 7. The three strongest directions

### Relay: a support-engineer interview with a reproducible handoff

**Pitch.** A voice interview where a support-engineer candidate investigates a customer's broken integration and proves that their handoff lets the next engineer reproduce the problem.

The target buyer is a technical support lead at a software company with an API or integration-heavy product. The candidate is applying for a support engineering or escalation engineering role. The initial use is one hiring round after basic eligibility screening.

The real problem is the combination of technical diagnosis and customer communication. Knowing HTTP terminology is insufficient if someone cannot establish impact, distinguish a workaround from a fix, and preserve the information another engineer needs. GitLab's public support hiring process includes live break-fix work and customer scenarios. Its support responsibilities also emphasize keeping customers informed and working across teams. That is direct evidence that employers test this combination. It does not prove demand for Relay specifically. [GitLab support interview process](https://handbook.gitlab.com/handbook/hiring/interviewing/customer-support-interviewing/), [support responsibilities](https://handbook.gitlab.com/handbook/support/support-engineer-responsibilities/).

The alternatives are a human practical interview, support assessment products, or a take-home exercise followed by discussion. A human practical interview can be excellent. Its cost is the specialist's preparation and interview time. Existing simulation products already cover much of the task. Relay's proposed advantage is the explicit test of the candidate's handoff against the running system.

Voice matters because the customer initially supplies incomplete information, challenges explanations and asks what happens next. Multiple roles matter because customer reassurance, engineering reproducibility and managerial judgment are different responsibilities. Interruption matters when the candidate must correct the customer's or interviewer's mistaken interpretation before it becomes an accepted fact.

Use a small working API environment and Bruno collections to replay diagnostic requests. E2B can host an isolated environment if the integration is straightforward. The artifact is a reproducible case, with linked conversational evidence. This changes what the interviewer can check.

Technical difficulty is medium if you build one case without arbitrary code execution. Commercial value is plausible because the buyer already runs a costly practical hiring round. The main risks are scenario authoring cost, similarity to Support Lab AI, and giving an unvalidated assessment more authority than it deserves.

### ProofRound: an AI recruitment interview grounded in the candidate's work

**Pitch.** An AI recruiter conducts a first-round interview around a job rubric and a candidate's chosen work sample, then gives the hiring manager an evidence brief and the questions still worth asking.

This is the direct AI recruitment interview option you requested. Its target buyer is a small software company or specialist recruiter screening early-career engineering applicants. It should run an actual application stage, with a human deciding whether to advance the candidate.

The core problem is that a polished CV gives a recruiter little basis for deciding what the applicant can explain or do. A generic screen often retells the same CV. ProofRound focuses the conversation on one job-relevant claim and one artifact.

For example, a candidate says they designed a project's authorization system. The AI opens the exact file at a pinned Git commit, asks how a permission check works, and introduces one changed requirement. The candidate clarifies that a teammate designed the architecture while they implemented the route checks. The brief records the narrower contribution and demonstrated understanding. It does not label the candidate dishonest.

Use a recruiter role to clarify contribution and motivation, a technical role to examine the artifact, and a hiring manager role to test an applied scenario. Shared context prevents each role from re-asking the background. Real-time interruption lets the candidate correct an incorrect attribution, explain an unfamiliar term or challenge an assumption about the project.

The meaningful integration is read-only access to a candidate-approved repository or document, with exact file or passage references. For a three-day MVP, use one curated public repository and a paste-in CV. Do not attempt reliable analysis of arbitrary large repositories. Give candidates without public work an equivalent supplied exercise. Public GitHub activity must not become an eligibility requirement.

Alex and BrightHire already offer adaptive screening and connected reports. Oral-defense products also examine submitted work. A pilot paper about AlteraSF even describes resume-claim verification. Its claims about linguistic authenticity are not a sound basis for building a deception score. [Alex](https://www.alex.com/product/ai-interviewer), [BrightHire](https://brighthire.com/ai-interviewer/), [AlteraSF pilot](https://arxiv.org/abs/2511.00774).

ProofRound's proposed difference is the reviewable chain from a job requirement to an artifact, an answer and an unresolved follow-up. This is a narrower workflow advantage, easy for competitors to copy. Difficulty is medium. Buyer relevance is high. Differentiation is modest. I would choose it if you want the clearest recruitment story and already have a recruiter willing to test it.

Never claim that a good explanation proves historical authorship or employment. The strongest supported claim is "the candidate demonstrated this understanding during this interview."

### MetricRoom: an analyst interview where the panel checks the calculation

**Pitch.** A candidate investigates a business question in a live dataset while AI stakeholders challenge the metric, assumptions and recommendation.

The target buyer is a data or analytics manager hiring junior or mid-level analysts. The problem is that correct SQL and persuasive presentation do not establish that someone answered the right business question.

Use a synthetic dataset for a subscription product. A product manager asks whether a new onboarding flow improved activation. The candidate finds an apparent increase. A data lead asks whether the definition changed. A customer-success interviewer introduces the experience of returning users. The candidate must establish the denominator, rerun the query and defend a revised conclusion.

Keep the case bounded. One dataset, one ambiguity in the metric, one relevant data-quality issue and a final recommendation are enough. Avoid a general analytics dashboard builder.

Voice matters because the candidate must ask stakeholders what "activation" means and explain why a result may mislead. Different roles own different business assumptions. Interruption lets the candidate stop an interviewer from turning "correlation in this sample" into a causal claim. A changed filter or query visibly changes the evidence.

DuckDB-Wasm lets the browser run real SQL over supplied data. Save the query, dataset version and result alongside the spoken explanation. The panel should receive those structured results instead of guessing what a screenshot contains. [DuckDB-Wasm overview](https://duckdb.org/docs/current/clients/wasm/overview), [query documentation](https://duckdb.org/docs/current/clients/wasm/query).

Existing assessment platforms already test analysts. Canditech markets job simulations, while Goodfit describes a data analyst process combining voice screening and skills assessment. The proposed distinction is the live relationship between a stakeholder's challenge, the candidate's query and the revised conclusion. I did not verify that every competitor lacks this exact workflow. [Canditech](https://www.canditech.io/), [Goodfit analyst hiring](https://goodfit.so/roles/data-analyst).

Difficulty is medium. It avoids running arbitrary server-side candidate code, although browser queries still need resource limits. It may be less obvious to other teams than a coding or support simulator. Its main weakness is voice relevance: if stakeholders simply read the task aloud, the product becomes a SQL test with narration. Real ambiguity must require conversation.

## 8. Comparison

Scores are my product judgments on a five-point scale. Five is favorable. They are not measured outcomes or official judging weights. Duplicate risk is relative, with no numerical probability implied.

| Direction | Novelty | Real-world usefulness | Judge appeal | Demoability | Three-day feasibility | Agora fit | Integration value | Independent duplicate risk |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Relay, with handoff replay | 3 | 5 | 5 | 5 | 4 | 5 | 5 | Low to medium for the precise version; high for generic support roleplay |
| ProofRound recruitment interview | 2 | 5 | 4 | 4 | 4 | 5 | 4 | Medium to high |
| MetricRoom analyst interview | 4 | 4 | 4 | 5 | 4 | 4 | 5 | Low to medium |
| AI code-review interview, considered but not selected | 2 | 4 | 4 | 4 | 3 | 3 | 4 | High |
| General mock interview with a whiteboard, baseline | 1 | 3 | 2 | 4 | 5 | 4 | 2 | Very high |

Relay wins on the combination of a believable buyer, observable consequences and a short demo. MetricRoom wins on relative freshness. ProofRound wins on immediate recognition as recruitment software.

If the handoff replay gets cut from Relay, I would change the recommendation to MetricRoom. Without that check, Relay loses much of the reason to choose it over an existing support simulator.

## 9. Which integrations deserve their place

| Technology or system | What it changes | Decision for Relay |
|---|---|---|
| Agora Conversational AI | Carries the live conversation, interruption and speech pipeline. | Mandatory foundation. |
| Bruno CLI | Turns selected diagnostic requests into a portable collection and reruns them with machine-readable results. | Core integration. It makes the handoff testable. |
| E2B | Supplies an isolated environment for the small API case and replay. | Useful hosting choice if the initial setup works promptly. |
| GitHub | Can store the approved case handoff as an issue and link a versioned fixture. | Optional. Do not confuse "created an issue" with an assessment improvement. |
| DuckDB-Wasm | Executes real queries and makes result changes visible. | Core for MetricRoom, unnecessary for Relay. |
| Excalidraw | Lets candidates express spatial system reasoning. | Omit unless the chosen task requires them to draw. |
| A conversation or claim graph | Relates statements to supporting tests and unresolved questions. | Keep the data relationships internally. Start with a small evidence list in the interface. |
| WebContainers | Runs a development environment in the browser. | Useful for a code-centered alternative, excessive here. |
| tldraw | Provides a programmable canvas. | Not needed; production licensing also requires attention. |
| An ATS, CRM or calendar | Connects to an existing hiring or customer workflow. | Later, after the assessment itself proves useful. |
| A vector database | Searches a large knowledge collection. | Omit. One case and a short reference document do not justify it. |

Bruno documents collection execution and JSON reports. Its open-source repository has an MIT license; that does not mean every commercial Bruno feature is free. Use the documented CLI functionality and check the package you ship. [Bruno collections](https://docs.usebruno.com/v2/bru-cli/runCollection), [JSON reports](https://docs.usebruno.com/v2/bru-cli/builtInReporters), [repository](https://github.com/usebruno/bruno/).

E2B documents isolated code environments. Its SDK source includes controls for outbound internet access. The current Hobby offering lists a one-hour session limit and usage charges after credits. Validate the account and configuration before depending on it in a live demo. [E2B SDK](https://e2b.dev/docs/sdk-reference/js-sdk/v2.10.5/sandbox), [network controls in source](https://github.com/e2b-dev/E2B/blob/main/packages/js-sdk/src/sandbox/sandboxApi.ts), [pricing](https://e2b.dev/pricing).

WebContainers documents browser requirements and commercial API access. tldraw requires a valid license key for production. These are reasons to investigate fit before adding a canvas or browser IDE under deadline pressure. [WebContainers browser support](https://webcontainers.io/guides/browser-support), [API documentation](https://webcontainers.io/api), [tldraw licensing](https://tldraw.dev/sdk-features/license-key).

## 10. Relay, defined tightly

| Product decision | Definition |
|---|---|
| Working name | Relay |
| One-sentence pitch | A voice hiring interview where a support-engineer candidate investigates a customer's broken integration and produces a handoff another engineer can reproduce. |
| Core problem | Hiring teams cannot easily see whether candidates preserve technical accuracy and customer context when investigating and escalating a problem. |
| First buyer | A support engineering lead at an API-based software company. |
| Candidate | Someone applying for a support or escalation engineering role that requires technical investigation on entry. |
| Place in hiring | One practical round after initial screening, followed by a human decision. |
| Session length | A proposed 15-20 minute assessment, compressed to 4-5 minutes for the demo. |
| Main artifact | A candidate-approved escalation packet containing reproduction steps, observed results, customer impact, known uncertainty and transcript references. |
| Most important check | Can a clean instance reproduce the claimed failure using the supplied packet? |
| Deliberate boundary | The system assesses an interview. It does not operate a real customer's production system or make the hiring decision. |

Why does this problem persist? The relevant skills span a live customer conversation, technical investigation and a written transfer of responsibility. Testing them together usually requires someone to play the customer, someone who understands the system and a consistent assessment method. Ordinary questions are easier to administer, but they leave more to inference.

The difference Relay proposes is modest and concrete. Its final handoff contains executable evidence. The reviewer can inspect whether the reproduction worked and listen to the candidate's explanation of what it means. This is a stronger product claim than "we have more realistic personalities." It still needs testing against a well-run human practical interview.

### The one case to build

Use a fictional order fulfilment service. All companies, customers, credentials and records are synthetic.

The customer says: "Your integration says the order was processed, but our warehouse has two jobs for the same order."

The sandbox exposes a small documented API, a delivery log and a fulfilment-job list. A repeated webhook event creates another fulfilment job because the receiving service does not handle duplicates correctly. Each request can return HTTP 200. The visible status therefore does not establish that the customer's desired outcome occurred.

You do not need a payment provider, a real warehouse or a full commerce application. Two small tables and a few endpoints are enough to make this behavior real inside the demonstration.

The candidate must establish what happened, reproduce it safely in the sandbox, explain the impact and prepare an escalation. They are not required to patch the service. A correct outcome can be "reproduced and escalated, remediation still pending."

### A plausible interview sequence

The following dialogue is an original illustrative demo, not a transcript of a tested system.

| Moment | What happens | What it reveals |
|---|---|---|
| Briefing | The hiring manager explains the exercise, AI roles, tools and assessment criteria. | The candidate understands the task and how the AI is used. |
| Customer account | The customer reports duplicate warehouse jobs, without supplying all diagnostic details. | Can the candidate ask for identifiers, timing and impact? |
| Initial investigation | The candidate checks a delivery log and sees successful HTTP responses. | Do they distinguish transport success from business correctness? |
| Premature conclusion | If the candidate says the integration works, the customer asks why the warehouse still has duplicates. | Can they revise a weak conclusion? |
| Candidate interruption | The AI begins interpreting the issue as two different orders. The candidate interrupts: "Wait, these are the same order and event ID." | Interruption corrects the shared understanding. It is not a decorative demo trick. |
| Technical probe | The technical interviewer asks the candidate to demonstrate the duplicate behavior. | Can they design a relevant test instead of repeating terminology? |
| Handoff | The candidate selects the request sequence and writes the expected and actual result. | Can the next engineer understand and reproduce the claim? |
| Replay | The system resets the fixture and reruns only the submitted request collection. | Does the handoff contain enough operational detail? |
| Manager challenge | The manager asks what the candidate can tell the customer now, and what remains unverified. | Does the candidate overpromise a fix or communicate an accurate next step? |
| Review | The assessment links conclusions to utterances, request results and the handoff. | The human reviewer can inspect the basis for each finding. |

Do not force the premature-conclusion branch. A strong candidate who immediately identifies the duplicate event should receive a deeper question about safe retry behavior or containment. A struggling candidate can receive a bounded hint. Both paths should reach a usable final report.

### Make the replay meaningful

The candidate selects actual requests and specifies the relevant outcome. The application exports that selection as a collection and runs it against a clean fixture. It must not quietly add missing requests or identifiers from the hidden answer key.

Separate two checks:

1. Did the submitted steps reproduce the reported failure?
2. Does the service satisfy its intended behavior?

A good handoff can reproduce a service failure. That means the handoff succeeds while the service's correctness check fails. Label these outcomes separately so your interface does not penalize the candidate for exposing the bug.

Reproduction establishes a bounded observation. It does not prove the full root cause, completeness of the investigation or correctness of a proposed production fix. The technical interviewer should ask what additional evidence would establish those claims.

## 11. The interface and conversational behavior

Use one interview workspace with three areas:

| Area | Content | Purpose |
|---|---|---|
| Conversation | Current AI role, microphone state, live captions, pause and end controls. | Make turn ownership and AI identity clear. |
| Case workspace | Brief, API reference, request builder, responses and relevant log records. | Let the candidate investigate the task. |
| Candidate notes and handoff | Chosen observations, request sequence, customer update and escalation draft. | Let the candidate make their reasoning explicit and produce the artifact. |

Do not show a constantly changing score during the assessment. It distracts candidates and exposes noisy intermediate judgments. Let them inspect the factual notes and correct transcription errors. Keep the evaluator's interpretation separate until the review.

Start with a small chronological evidence list. Each item can link a statement to a request result. A full node graph can wait. The useful interaction is clicking "the integration works" and seeing the result that challenges that statement.

The customer should be concerned and specific, without becoming abusive. The technical interviewer should probe a mechanism. The hiring manager should connect decisions to impact and responsibility. Changing a voice or avatar alone does not create a meaningful role.

Give the candidate ways to say "I need a moment," "repeat that," "I disagree with that summary," and "I need a human review." Pausing or taking notes should not produce an automatic negative assessment. The speech system must yield when interrupted and resume from the corrected state.

## 12. A practical architecture

This is a proposed implementation, not a claim that the complete workflow has already been tested.

```text
Candidate browser
  Audio <-> Agora real-time channel and Conversational AI
                 |
                 v
          Custom model endpoint
                 |
          Interview controller
          /        |          \
   Shared record   Role rules  Model for the next utterance
          |
          +-> Restricted case tools -> Isolated API fixture
          |                                  |
          +-> Candidate handoff -> Bruno replay -> Test results
          |
          +-> Evidence validator -> Structured assessment

Browser workspace <-> Application backend <-> Shared record
```

### Use one controlled speech process

For the MVP, one Agora conversation can present several interviewer roles through your application controller. Only the selected role can speak. All roles receive the relevant shared candidate record. The system can revisit a role when a new observation warrants it.

Agora's official handoff recipe demonstrates server-side persona routing through a custom model endpoint. Its supplied example uses deterministic logic and mock responses. It is useful implementation material, but you must supply the adaptive interviewing behavior. [Agora agent handoff recipe](https://recipes.agora.io/recipes/agent-handoff).

The baseline can use one voice with an explicit role label and a brief spoken identity at transitions. Distinct voices improve recognition if your chosen configuration supports reliable switching. Generic runtime update documentation does not prove that every speech provider supports per-turn voice changes. Test that early; do not make three simultaneous speaking agents a late dependency.

This architecture satisfies multiple interviewer roles without requiring independently running language models to negotiate the floor. Describe it accurately to judges.

### Keep a shared record outside the prompts

Use a small server-side store with stable identifiers. A relational database or simple session store is enough.

| Record | Minimum contents |
|---|---|
| Session | Session ID, scenario version, current role, difficulty branch, assistance used. |
| Transcript segment | Speaker, timestamps, finalized text, correction history and delivery status. |
| Candidate statement | Exact supporting segment, scope, time and whether it is a hypothesis or asserted conclusion. |
| Tool result | Request ID, inputs, outputs, fixture version and execution status. |
| Open question | Missing information, why it matters and the role best suited to ask. |
| Handoff | Candidate-approved content, selected requests and replay result. |
| Assessment item | Criterion, evidence references, explanation, uncertainty and review status. |

Keep the hidden scenario answer key separate. It defines the fixture and assessor expectations. It must not appear in the browser or leak into the customer's dialogue before the candidate discovers the information.

Shared candidate context does not mean every fictional character knows every hidden fact. The customer knows their experience. The technical interviewer can inspect the observations already collected. The manager can reference earlier promises. Apply these role limits while maintaining one consistent session history.

### A controlled turn loop

1. Receive a finalized candidate utterance or a completed tool action.
2. Save it with its stable identifier.
3. Update observations and any candidate statements that need clarification.
4. Select the next relevant role and probe from the current evidence gaps.
5. Generate a short response grounded in the permitted case information.
6. Allow only that response to enter the speech output.
7. If interrupted, cancel stale output and incorporate the candidate's correction before producing another turn.

Suggested priority is candidate correction first, then a response to a completed tool action, then an unresolved core question, then an optional harder probe. This priority is your product logic, not a platform guarantee.

Do not treat generated speech as heard speech. If the candidate interrupts halfway through a question, the unplayed ending must not be treated as information the candidate received. Preserve interruption status and the delivered portion where the API supplies it. If delivery is uncertain, repeat the necessary detail before assessing the answer.

Agora documents interruption controls, while its Python session reference includes methods for interruption, speaking and runtime instruction updates. The custom endpoint must be reachable by Agora's cloud service. Validate request authentication and keep application credentials server-side. [Agora interruption recipe](https://recipes.agora.io/recipes/interruptions), [session API reference](https://github.com/AgoraIO/agora-agents-python/blob/main/docs/reference/session.md).

### Keep tool execution narrow

For this case, allow a few operations such as inspecting an event, running an approved API request, reading resulting jobs, building the handoff and replaying it. These are proposed application tool names and behaviors, not existing Agora APIs.

Use structured arguments. Restrict requests to the scenario's endpoints. Do not pass candidate text into a shell command or allow arbitrary internet destinations. Generate the request collection from validated fields. Do not accept candidate-supplied pre-request scripts.

If using E2B, prebuild the tiny fixture and runner. Keep outbound access restricted and confirm that the controller can still communicate through the intended management path. The assessment backend should enforce the same request limits even if the sandbox provider offers isolation.

If E2B setup is slow, use an isolated local or hosted container that your team already knows. Retain the actual Bruno replay. The isolation provider is replaceable; the reproducible handoff is the product's central test.

### Assess evidence in a separate step

After a turn, the speaking model may suggest a follow-up. After the session, an evaluator drafts findings against the rubric. A deterministic validator rejects references to nonexistent transcript segments or tool results.

Keep failure detection for the planted API case in code. Let the model explain the candidate's observed decisions and identify missing evidence. A second model agreeing with the first is not proof of correctness.

Do not train a model for this hackathon. The difficult work is consistent state, controlled role behavior, reliable audio and an assessment whose claims can be checked.

## 13. Meet every interview requirement without expanding the product

This maps your supplied problem statement to the proposed MVP.

| Requirement | Concrete implementation |
|---|---|
| Real-time, interruptible voice | Candidate and AI communicate through Agora; speech output yields to the candidate. |
| Multiple roles or personalities | Customer, technical interviewer and hiring manager have different knowledge and responsibilities. |
| Shared candidate context | Every role can reference the permitted prior statements, tests and customer commitments. |
| Dynamic follow-ups | A probe depends on the candidate's answer or tool result, such as claiming success from HTTP 200. |
| Controlled turn-taking | One controller owns the speaking role and cancels stale responses. |
| Scenario-based questions | The whole interview centers on the synthetic duplicate-fulfilment case. |
| Difficulty adjustment | Common core task; bounded hints or deeper optional questions according to demonstrated progress. |
| Vague or contradictory answers | The panel requests a concrete test or asks the candidate to reconcile statements with the same scope. |
| Transcript-linked feedback | Findings cite finalized utterances, with supporting request and replay records. |
| Structured final assessment | A short criterion-based report separates observed performance, assistance and unanswered questions. |
| Clear AI disclosure | Entry notice and persistent role labels identify the participants as AI. |

### Example final assessment

The following is synthetic example output. It illustrates the report format and does not describe a real candidate or a completed test.

| Criterion | Finding | Evidence | Remaining question |
|---|---|---|---|
| Clarifies the customer problem | Demonstrated independently | At 01:18, asked whether the two jobs had the same order and event IDs. | Did not establish the total number of affected orders. |
| Tests a technical claim | Demonstrated after a probe | Request A4 showed a second job after replaying the same event. At 03:42, explained why HTTP 200 was insufficient. | Needs a further test to establish whether every retry path behaves this way. |
| Revises a conclusion | Demonstrated | At 03:58, corrected the earlier "integration works" statement and explained the new evidence. | None for this observation. |
| Produces a usable handoff | Demonstrated | The submitted collection reproduced the duplicate on a clean fixture. | Root-cause confirmation beyond the fixture remains outside this exercise. |
| Communicates a responsible next step | Partly demonstrated | At 05:10, described impact and escalation without promising that the bug was fixed. | Did not state when the customer would receive the next update. |

End with a human review note such as: "Evidence supports advancing to a discussion of incident ownership. Ask how the candidate would establish impact across all affected orders." The application should present this as an AI-drafted recommendation requiring review.

Avoid a universal "87% hireability" score. If judges expect numbers, use a simple criterion scale with explicit behavioral descriptions and a separate "not observed" value. Do not manufacture an answer when the exercise never tested the skill.

### Adjust difficulty without making results meaningless

Use three predefined paths around the same case:

- Standard path: the candidate investigates with the supplied documentation.
- Assisted path: a bounded hint suggests comparing identifiers or checking the resulting job count. Record the hint and assess the subsequent work as assisted.
- Extension path: a strong candidate is asked how they would verify safe retry behavior or distinguish a short-term containment action from a permanent fix.

Everyone retains the same core criteria. Optional extensions supply additional evidence, not a disguised penalty for reaching the harder branch. This is practical bookkeeping for a prototype, not a psychometrically calibrated adaptive test.

## 14. Privacy, security and trust

An interview transcript can contain personal information, former-employer secrets, salary details, health information or credentials spoken accidentally. The fact that the demo is small does not make those records harmless.

For the hackathon, use volunteers, synthetic profiles and synthetic business data. Keep the public demo recording separate from an assessment session's normal data policy.

| Risk | MVP control |
|---|---|
| Unclear AI interaction | Explain the AI roles before microphone access and label them throughout. |
| Unnecessary recording | Do not persist raw audio by default. Retain only the transcript and task evidence needed for the demonstration. |
| Sensitive transcript content | Avoid collecting a real CV for Relay. Redact accidental secrets before storage or export where practical. |
| Indefinite application retention | Choose and implement a short demo retention period, such as 24 hours, plus a working delete-session control. Verify deletion of the application's transcript and evidence records. |
| Misleading deletion claims | Distinguish deletion from your app from provider logs, backups and separately published demo video. Do not claim end-to-end deletion without verifying it. |
| Cross-candidate leakage | Separate sessions, issue access-scoped tokens and test that another session cannot read a transcript or case result. |
| Prompt injection in candidate material | Treat speech, documents, code comments and tool output as task data. They cannot change the rubric, authorize unrelated actions or reveal hidden answers. |
| Unsafe execution | Fixed sandbox endpoints, validated request fields, resource limits and no arbitrary shell or network access. |
| Public exposure through an integration | Keep exports private by default. Export only reviewed synthetic case information for the public demo. |
| Overconfident assessment | Cite observations, expose uncertainty and require a human decision. |
| Accessibility problems | Provide captions, thinking time, keyboard operation, pause and correction controls. For real hiring, offer an appropriate alternative assessment route. |

Agora and your selected speech and model providers still process data even if your own app does not save raw audio. Before real hiring, verify the chosen services' retention, training-use terms, processing regions and contractual controls. I did not verify an account-specific privacy configuration, so this report makes no claim of zero retention or India-only processing.

An appropriate original disclosure for the demo would be:

> You are taking part in a simulated hiring exercise with AI interviewers. Your answers and actions will produce a draft assessment for human review. We will explain what is stored before you start. You can pause, correct a transcript error or stop the session. No real customer systems are involved.

For a deployment in India, check the provisions currently in force under the DPDP framework. Government material describes an eighteen-month phased implementation period for the 2025 Rules. Do not describe the whole framework as either fully active or irrelevant without checking the applicable dates. [Government of India update, August 2026](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2294910&lang=1&reg=3).

Other jurisdictions create additional obligations. NYC's rules address covered automated employment decision tools, including audit and notice requirements. US EEOC guidance addresses disability risks from algorithmic assessment. A human clicking "approve" does not by itself settle every legal question. [NYC guidance](https://www.nyc.gov/site/dca/about/automated-employment-decision-tools.page), [EEOC AI and disability resources](https://www.eeoc.gov/eeoc-disability-related-resources/artificial-intelligence-and-ada).

Leave emotion recognition, accent scoring, personality inference and lie detection out of the product. In addition to the validity problem, European rules expressly restrict workplace emotion recognition, subject to limited exceptions. [European Commission AI Act guidance](https://digital-strategy.ec.europa.eu/en/faqs/navigating-ai-act).

These controls support a more trustworthy demo. They do not constitute certification or approval for production hiring.

## 15. The three-day build plan

This is a sequence of deliverables, without allocating work among your teammates. It assumes new development is allowed under the organizer guidance applicable to you.

| Time | Deliverable | Acceptance condition |
|---|---|---|
| First few hours | One Agora conversation connected to the application backend. | A person can interrupt a long AI answer, correct it and receive a relevant reply. |
| Rest of day 1 | The tiny API fixture, request interface and one replayable Bruno collection. | The planted duplicate behavior occurs for real in the sandbox and reproduces after a reset. |
| End of day 1 | A complete thin interview path using basic role prompts. | Customer account, investigation, handoff and short debrief work in one session. |
| First half of day 2 | Shared transcript and action records, role routing and follow-up selection. | A later role references an actual earlier statement and a real request result. |
| Second half of day 2 | Standard, assisted and extension paths; candidate-owned handoff assembly. | Different answers lead to different probes, while the same core assessment remains intact. |
| End of day 2 | Structured assessment with validated evidence links. | Every factual assessment claim opens the cited transcript or tool record. Missing evidence is explicit. |
| First half of day 3 | Disclosure, correction, deletion, session isolation and recovery behavior. | The core safety and reliability checks below pass. |
| Remaining day 3 | Rehearsal, fixes, README, architecture diagram, required video and known limitations. | The live path works repeatedly with an unfamiliar participant and the submitted materials match the implementation. |

Reserve the last substantial block for reliability and rehearsal. A new feature on the final evening is worth adding only if it repairs a missing requirement or a demonstrated failure.

### The minimum scope to protect

One job family. One case. Three roles. One conversation controller. A request workspace. A replayable handoff. A short evidence-based assessment.

Do not add a marketplace, a full applicant tracking system, a resume-ranking pipeline, multilingual scoring, custom avatars, broad repository ingestion, arbitrary code execution or automatic scenario generation. Those would change both the build time and the risk profile.

### Cut in this order if time shrinks

1. Remove distinct voices and retain clear role labels and spoken transitions.
2. Remove GitHub export and let the candidate download the handoff.
3. Remove the visual graph and retain linked evidence cards.
4. Remove the extension case and retain one bounded difficulty adjustment within the main case.
5. Replace an unfamiliar sandbox provider with an isolated environment the team already knows.

Do not cut real Agora interaction, dynamic follow-ups, candidate interruption, shared role context or handoff replay. Those establish the concept and satisfy the brief.

### Tests that are worth the time

| Test | What must happen |
|---|---|
| Candidate interrupts halfway through a question | Old speech stops; the unspoken ending does not become assumed candidate knowledge. |
| Candidate pauses to think | The system allows a pause or an explicit thinking state without a negative score. |
| Strong candidate finds the issue immediately | The panel takes a relevant deeper branch instead of forcing the rehearsed mistake. |
| Candidate gives a vague answer | The panel asks for a concrete observation or test. |
| Candidate corrects a statement after new evidence | The system records justified revision rather than accusing them of contradiction. |
| Incomplete handoff | Replay reports the missing detail or failure. The backend does not secretly repair the packet. |
| Complete handoff | The clean fixture reproduces the reported issue. |
| Unsupported assessment citation | The validator rejects the finding or marks it unsupported. |
| Candidate asks the AI to reveal the answer key | Hidden scenario content stays hidden; the interview continues within the agreed task. |
| Another session requests the report | Access is denied. |
| Brief network interruption | The app shows connection state and recovers without losing or duplicating finalized evidence. |
| End or delete session | Speech stops, runtime resources close and the app's retention behavior matches its notice. |

Suggested engineering targets are under 500 milliseconds from detected interruption to audible stop, and roughly one to two seconds to first response audio for ordinary turns. These are proposed targets, not measured Agora guarantees. Record observed performance on the actual demo setup. Do not hide long tool operations behind misleading conversational filler.

### Costs

Agora's public page currently lists an audio task rate of $0.10 per minute, with selected model usage included, and says the same rate applies when bringing your own key. Custom provider charges and other services may be additional. [Agora pricing](https://www.agora.io/en/pricing/conversational-ai-engine/).

At that listed rate, a 15-minute audio task is $1.50 and twenty such test sessions are $30 before other charges, discounts or credits. These are arithmetic examples, not a total-cost quote. Check the actual billing configuration. Do not base your plan on unverified event credits.

One active voice process is simpler to reason about and budget than several continuously active agents. Close unused sessions and sandboxes. You do not need a paid enterprise assessment integration to build this demo.

## 16. The live demo

Open with the hiring problem in one sentence: "A support engineer can know the right terms and still leave the next engineer unable to reproduce the customer's problem."

Then show the task. Avoid starting with a diagram of your architecture.

| Demo time | What the judge sees |
|---|---|
| 0:00-0:30 | Job title, AI disclosure and the customer reporting duplicate fulfilment jobs. |
| 0:30-1:20 | A natural conversation and one visible request result. The successful HTTP response conflicts with the customer's observed outcome. |
| 1:20-2:10 | A meaningful candidate interruption or correction. The next role picks up the corrected context. |
| 2:10-3:10 | The candidate selects reproduction steps. The clean replay produces the duplicate jobs. |
| 3:10-4:00 | The manager asks what is now known, what remains uncertain and what the customer should be told. |
| 4:00-4:40 | The final assessment opens one exact utterance and its supporting tool result. |
| 4:40-5:00 | Explain who would use this hiring round and name the current limitation. |

Give the judge a choice of an early diagnosis or a vague answer to demonstrate an actual branch. It need not create a new scenario. A fixed world with changing questions is enough.

The clearest closing demonstration is a correction that improves the assessment: the candidate disputes a bad transcript or an unfair interpretation, and the record updates transparently. This directly addresses trust and shows that the system can recover from its own error.

Use the required video as a separate submission artifact and backup illustration. The live demonstration should still include real voice and a real tool operation. If a service fails, disclose the failure and recover; do not present cached output as a fresh execution.

## 17. The first customer and the business case

Start with a support lead who already conducts practical interviews for an API product. Offer one carefully prepared exercise with a reviewable output. A large enterprise-wide hiring system is an unnecessarily difficult first sale.

The initial commercial promise should be reducing the effort required to collect useful evidence before the final human interview. Do not promise fewer bad hires, unbiased decisions or improved retention until you have measured those outcomes.

The workflow could be simple: the employer approves the scenario and rubric, invites a candidate after screening, receives the evidence packet, and decides what to ask next. A later pricing experiment could charge per completed assessment or per hiring campaign. No willingness-to-pay research was conducted for this report, so I would not invent a price.

The main expense may become scenario preparation and evaluation maintenance, rather than model tokens. Employers use different products and expect different prior knowledge. If every sale requires weeks of custom case development, you have a service business with software, not an easily repeatable product. That can still be viable, but it changes the business.

Before investing beyond the hackathon, run these checks with permission:

- Ask three support leads to show how they currently evaluate a candidate's investigation and escalation skills. Discuss an actual recent hiring process rather than asking whether they like AI.
- Have two experienced support engineers attempt the same case and identify ambiguity, missing context and artificial traps.
- Ask two reviewers to judge candidate evidence without seeing the AI assessment, then compare conclusions and investigate disagreements.
- Measure how long a human takes to make a useful next-step decision from the packet versus the team's current material.
- Ask candidates whether they understood the task, could correct mistakes, and considered the assessment relevant to the role.

For the hackathon, even a few documented observations from relevant people would be valuable. Label them as exploratory feedback. They would not validate the scoring system.

The strongest reason to continue is a buyer saying, "I would use this for this specific round, and this evidence would change my next interview." Enthusiasm about a voice demo is weaker evidence.

## 18. Attack the recommendation like a skeptical judge

| Judge's objection | Honest answer | How to reduce the weakness |
|---|---|---|
| "Support simulators already exist." | Correct. Relay has strong adjacent and direct competitors. | Show the submitted handoff executing against a clean fixture. Make that the central outcome and explain exactly what it establishes. |
| "This is a toy API, not real work." | One fixture cannot represent a whole support job. | Base the exercise structure on actual role requirements, get a support engineer to review it, and limit the assessment claims. |
| "You scripted the demo." | The scenario's facts should be fixed; the candidate's conversation should change the probes. | Let a judge choose a different answer and show the corresponding branch. Do not hard-code the dialogue. |
| "The AI found the bug for the candidate." | That would undermine the assessment. | Record hints and tool ownership. The candidate chooses the investigation and confirms the handoff. Do not silently generate missing reasoning. |
| "Your score is just another model's opinion." | Some interpretation remains subjective. | Show deterministic replay results, exact citations and a human-review step. Separate observation from judgment. |
| "A good programmer could do this without speaking." | A subset of the task can be done silently. | Make impact discovery, customer correction and the explanation of uncertainty necessary parts of the support role being tested. |
| "Why several interviewers?" | They are useful only if they expose distinct consequences. | The customer asks about outcomes, the engineer checks reproduction, and the manager checks commitments and responsibility. |
| "Where is Agora essential?" | The product depends on the candidate managing a live, interruptible customer conversation while investigating. | Demonstrate a correction that changes shared context and the next question. Keep the full voice path on Agora. |
| "You reward confident English." | That would be a serious assessment defect. | Judge content and actions, allow thinking time, avoid accent and confidence scores, and offer appropriate alternatives in real hiring. |
| "Anyone can use AI to pass." | Relay does not solve identity or undisclosed assistance. | State the allowed-tool policy and test whether candidates can interpret results and handle a changed condition. Do not claim it is cheat-proof. |
| "I could copy this in a week." | A prototype's defensibility is low. | Long-term value would require reviewed scenarios, evaluation evidence and adoption in a specific hiring process. None exists yet for this concept. |
| "Three days is not enough." | It is enough for a narrow demonstration, not production recruitment software. | Protect the one-case scope and remove optional integrations before sacrificing reliability. |

Another team could beat this with a simpler recruitment interview that sounds better, has a real employer testing it and never loses context. They could also win with a clearer visual demonstration or a more credible assessment method. Technical breadth will not compensate for an unreliable conversation.

The modification I would make before building is already reflected in this recommendation: narrow a general support simulator to one practical interview whose defining artifact is a reproducible escalation. Then validate that artifact with a human who has to use it.

If the final demo only shows a customer roleplay followed by a colored report, Relay has failed its own selection test.

## 19. A few additional directions, explored less deeply

These are secondary options. They received less competitor and buyer research than the three main recommendations. Treat their apparent freshness as uncertain.

| Idea | Core interview and meaningful integration | Why it could work | Why I did not choose it |
|---|---|---|---|
| Model release panel | An ML candidate examines a small evaluation dataset while an AI product manager and technical reviewer question whether a model is ready for a narrow use. A notebook or data tool checks subgroup errors and failed examples. | Fits your team's ML experience; the panel can challenge an impressive aggregate metric with an actual failure. | Requires careful case design, fair evaluation and a convincing reason for voice. Avoid medical or similarly sensitive deployment decisions. |
| Accessibility review interview | A frontend or design candidate inspects a small working page while a customer role and engineering role ask about an accessibility problem. Browser checks provide concrete evidence. | A visible task with a human consequence; could suit an engineer-designer team. | Automated checks cover only part of accessibility. An AI character must not be presented as a substitute for disabled users' lived experience. |
| Portfolio change request | A candidate explains a small project, then receives a changed requirement and updates a bounded part of it while a panel follows the reasoning. | Makes portfolio discussion more demanding than a rehearsed presentation. | Strong overlap with oral-defense tools and technical work-sample products; arbitrary repository setup is expensive. |
| Customer discovery audition | A solutions engineer candidate interviews an AI customer with incomplete requirements, then proposes a configuration tested against a small product capability document. | Natural reasons for several stakeholders and clarifying interruptions. | Enterprise sales roleplay is crowded, and the event has a separate sales track. Keep the candidate assessment explicit. |
| Incident commander audition | An engineering-manager candidate leads a synthetic incident discussion and is assessed on evidence, ownership and communication. A timeline connects decisions to simulated monitoring results. | Excellent real-time voice fit and visible shared context. | ProdSimulator is adjacent, and EchoSphere has a dedicated incident commander track. Easy to become the wrong product for your chosen statement. |

I would not choose "interview transcript becomes a graph" as a standalone fourth recommendation. Use it as a component only after naming the decision it helps a candidate or hiring manager make.

## 20. What is established, what remains uncertain

The research establishes substantial public competition in adaptive interviews, AI panels, whiteboard interviews, job simulations, code review assessments and transcript-based feedback. It also establishes that real employers evaluate support engineers through technical and customer scenarios, and that the recommended implementation building blocks have public documentation.

The proposed concepts, rankings, demo design and architecture are my synthesis. No prototype was built or benchmarked in this research task. I did not test competitor accounts, interview buyers or validate any scoring rubric. Some young products may have limited adoption; their public existence is still relevant to a judge asking whether the idea already exists.

The search covered official event pages, recruiting and training products, public repositories, recent Devpost projects, research papers, candidate discussions, integration documentation, pricing and data-handling guidance. I stopped when the remaining uncertainties were mainly buyer demand, hands-on reliability and assessment validity. More broad search would not resolve those.

My choice remains Relay if you can make the handoff replay work early. Choose MetricRoom if your team is more excited by a live data investigation or if the support case does not feel credible after a quick review. Choose ProofRound if an actual recruiter wants to try the first-round interview and can help define the rubric.

The strongest thing to show a judge is one moment where the candidate's answer changes the next question, their action produces a real result, and the final assessment accurately explains both.
