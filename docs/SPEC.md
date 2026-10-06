You are a senior software architect, full-stack engineer, BIM/Digital Construction systems engineer, QA engineer, UX designer, and technical writer.

Your task is to design and implement a complete portfolio-quality software project called:

# BIMGuard
## BIM Change Impact & Information Consistency Engine

The project is intended to demonstrate that I understand real engineering software problems relevant to a Japanese engineering/software company such as Hirate Technical Corporation.

IMPORTANT:
- Do NOT use my existing Loom project.
- Do NOT integrate Loom into this project.
- Do NOT build a generic AI chatbot.
- Do NOT build a generic CRUD dashboard.
- Do NOT create fake “AI magic” that simply sends everything to an LLM.
- The core value must come from deterministic engineering logic, dependency analysis, version tracking, BIM/document relationships, change detection, and release-readiness validation.
- AI should be an additional explanation/assistant layer, not the core intelligence.
- The application must be useful even if the AI functionality is completely disabled.

The final result should look like a small but serious commercial engineering-software prototype rather than a student CRUD application.

---

# 1. BUSINESS PROBLEM

Large BIM projects contain many interconnected information sources:

- architecture
- structural engineering
- MEP
- equipment
- schedules
- quantities
- drawings
- specifications
- supporting documents
- revisions
- approval/status information

A change to one model/document can affect many other files.

The difficult problem is not simply:

"Which version is newer?"

The more interesting problem is:

"What other information may now be outdated or inconsistent because this file changed?"

BIMGuard should provide an automated answer.

Example:

An architectural model changes from revision A-101 v12 to v13.

BIMGuard detects the change and determines that:

- S-201 may be affected
- M-301 may be affected
- Q-101 may be affected

It then determines:

- what changed
- what depends on the changed information
- which dependent documents are stale
- severity
- confidence
- why the relationship exists
- whether the project should be allowed to proceed to issue/release

The system should behave like an engineering "early warning" and "impact analysis" layer above normal BIM/document management.

---

# 2. IMPORTANT POSITIONING

Do not claim that the target company has a "bad" or "broken" system.

The product should be positioned as:

"An intelligent consistency and change-impact layer that complements existing BIM/CDE/version-management systems."

The project should demonstrate awareness that modern BIM workflows already provide:

- version control
- document history
- status management
- notifications
- CDE functionality
- naming rules

BIMGuard adds another layer:

VERSION MANAGEMENT
        +
CHANGE UNDERSTANDING
        +
DEPENDENCY ANALYSIS
        +
IMPACT ANALYSIS
        +
CONSISTENCY VALIDATION
        +
RELEASE READINESS

The key product statement is:

"Version control tells you what changed. BIMGuard tells you what that change could affect."

---

# 3. PRIMARY USER

Primary user:

BIM/project/engineering team member responsible for reviewing project information before issuing or distributing a revision.

Secondary users:

- BIM coordinator
- project engineer
- architect
- structural engineer
- MEP engineer
- project manager
- QA/review personnel

Do not assume every user is a programmer.

The interface must be understandable to engineers.

---

# 4. CORE PRODUCT WORKFLOW

The complete workflow should be:

1. Create a project.
2. Import BIM/document files.
3. Register files and revisions.
4. Extract metadata.
5. Register relationships/dependencies.
6. Build an information dependency graph.
7. Upload a new revision.
8. Compare revisions.
9. Detect meaningful changes.
10. Propagate the changes through the dependency graph.
11. Calculate impact.
12. Identify stale/possibly stale information.
13. Run consistency rules.
14. Run release-readiness validation.
15. Show the engineer exactly why something is blocked.
16. Allow the engineer to acknowledge/review issues.
17. Generate an issue-readiness report.
18. Optionally use AI to explain findings in natural language.

---

# 5. MVP SCOPE

Build a realistic MVP first.

The MVP must have these capabilities:

## A. Project management

Users can:

- create project
- view project
- rename project
- archive project
- delete project

Each project contains:

- project ID
- project name
- description
- client
- created date
- updated date
- project status

Example:

Project:
"Factory Expansion – Building A"

---

# 6. DISCIPLINES

Support at least:

- Architecture
- Structure
- MEP
- Equipment
- Quantity
- General

Use an extensible enum rather than hard-coding logic everywhere.

---

# 7. DOCUMENT MODEL

Create a document entity with:

- ID
- project ID
- document number
- name
- discipline
- file type
- status
- current revision
- author
- created date
- modified date
- issue date
- metadata
- source system
- checksum/hash

Example:

A-101
Level 2 Floor Plan
Architecture
Revision 12

---

# 8. REVISION MODEL

Every document must support revisions.

Example:

A-101

v10
v11
v12
v13

Each revision should contain:

- revision ID
- document ID
- revision number
- file path
- checksum
- upload timestamp
- created by
- status
- change summary
- previous revision ID

Statuses:

- Draft
- In Review
- Approved
- Issued
- Superseded
- Rejected

Never overwrite history.

Revision history must be immutable.

---

# 9. DEPENDENCY MODEL

This is the heart of the project.

Create explicit relationships between documents.

Example:

A-101
depends on
S-201

A-101
affects
M-301

Q-101
depends on
A-101

Relationships should have:

- source document
- target document
- relationship type
- confidence
- reason
- created by
- created timestamp

Relationship types:

- depends_on
- affects
- references
- generated_from
- derived_from
- spatially_related_to
- quantity_based_on
- validation_source
- approval_dependency

Do not make every relationship equivalent.

A structural dependency should have more impact than a simple reference.

---

# 10. DEPENDENCY GRAPH

Implement the project internally as a directed graph.

Example:

Architecture A-101
        |
        +----> Structure S-201
        |
        +----> MEP M-301
        |
        +----> Quantity Q-101

The system must be able to:

- find direct dependencies
- find indirect dependencies
- traverse the graph
- calculate impact radius
- rank impacted documents
- avoid infinite loops
- prevent duplicated results

Implement graph traversal using a clean service abstraction.

Do not put graph logic directly into frontend components.

---

# 11. CHANGE DETECTION

This is the core engineering feature.

When a new revision is uploaded, compare it with the previous revision.

The system should detect multiple change types.

At minimum:

### Metadata change

Example:

Status changed from Draft to Issued.

### Geometry change

For supported structured/sample BIM data:

- wall moved
- room changed
- door moved
- element added
- element removed
- element modified

### Parameter change

Example:

Wall:

length:
5000 → 5300

material:
Concrete → Steel

### Spatial change

Example:

Element moved from:

Room 203

to:

Room 204

### Classification change

Example:

Element category changes.

### Reference/dependency change

Example:

A document starts or stops referencing another document.

---

# 12. CHANGE DETECTION OUTPUT

Represent every detected change as a structured object.

Example:

{
  "element_id": "wall-204",
  "change_type": "GEOMETRY_CHANGED",
  "field": "location",
  "old_value": "...",
  "new_value": "...",
  "severity": "MEDIUM",
  "confidence": 0.96
}

Never rely on an LLM to determine whether a numeric field changed.

Use deterministic code.

---

# 13. BIM FORMAT SUPPORT

The MVP should NOT require proprietary Autodesk credentials.

The project must run locally.

Primary demonstration format:

IFC

Use a suitable open-source IFC parser.

The application should be designed around an abstraction:

BIMProvider

with an interface similar to:

- import_model()
- list_elements()
- get_element()
- get_properties()
- get_geometry()
- compare_models()

Implement:

1. IFC provider
2. Mock BIM provider for testing

Design the architecture so an Autodesk Platform Services adapter can be added later.

Do not pretend APS functionality exists if credentials are not configured.

---

# 14. SAMPLE BIM DATA

Create synthetic/sample data specifically for the demonstration.

Provide at least:

Project A:

Factory Expansion

Discipline files:

architecture_v1.ifc
architecture_v2.ifc

structure_v1.ifc

mep_v1.ifc

quantity_v1.json

equipment_v1.json

Create the data so architecture_v2 contains meaningful changes.

Example:

v1:

Room 204 wall:
x = 10.0m

v2:

Room 204 wall:
x = 10.3m

Also move a door.

Add a new wall.

Modify a room property.

This should generate meaningful downstream impacts.

---

# 15. IMPACT ANALYSIS ENGINE

After detecting changes, propagate their impact through the dependency graph.

Example:

Architecture A-101 changes.

Directly affected:

S-201
M-301
Q-101

Indirectly affected:

Equipment E-020

The engine should calculate:

- affected documents
- affected elements
- impact distance
- severity
- confidence
- impact reason

Example:

{
  "document": "S-201",
  "severity": "HIGH",
  "confidence": 0.91,
  "distance": 1,
  "reason": "Structural document depends on changed architectural geometry."
}

---

# 16. IMPACT SEVERITY MODEL

Implement a deterministic scoring system.

Example factors:

dependency strength
+
change type
+
graph distance
+
affected element type
+
document status
+
whether the dependency is issued/approved

Example conceptual score:

Impact Score =
Dependency Weight
× Change Weight
× Propagation Weight
× Status Weight

Then classify:

0–24:
LOW

25–49:
MEDIUM

50–74:
HIGH

75–100:
CRITICAL

Make these weights configurable.

Do not hide the algorithm.

Show the user WHY a score was generated.

---

# 17. STALE INFORMATION DETECTION

A document should become potentially stale when a dependency changes after its current revision.

Example:

A-101 v13 uploaded.

S-201 still depends on A-101 v12.

Display:

STALE DEPENDENCY

A-101:
current revision = 13

S-201:
validated against revision = 12

Severity:
HIGH

This must be deterministic.

---

# 18. RELEASE READINESS ENGINE

Create a dedicated validation engine.

Button:

"Validate for Issue"

Checks:

### Revision checks
- missing revision
- duplicate revision
- invalid revision sequence

### Dependency checks
- stale dependency
- missing dependency
- unresolved reference
- affected downstream document not reviewed

### Metadata checks
- missing author
- missing discipline
- missing status
- missing project ID

### Naming checks
Implement a configurable naming convention.

Example:

DISCIPLINE-DOCUMENTNUMBER-LEVEL-REV

Examples:

A-101-L02-R13
S-201-L02-R08

### Status checks
Prevent issuing a document with unresolved critical issues.

### Consistency checks
Compare known shared parameters.

### Approval checks
Do not allow issue if required approval is absent.

---

# 19. VALIDATION RESULT

Display:

PROJECT STATUS

❌ NOT READY FOR ISSUE

Critical:
2

High:
3

Medium:
4

Low:
1

Then:

Critical issue:

"Structural model references outdated architectural revision."

Details:

Architecture A-101
Current: v13

Structure S-201
Validated against: v12

Recommended action:

"Review structural model against A-101 v13."

---

# 20. ISSUE READINESS REPORT

Allow generation of a professional report.

Include:

- project information
- validation timestamp
- current revisions
- detected changes
- impacted documents
- unresolved issues
- severity
- dependency graph summary
- final readiness status

Support:

PDF
JSON
CSV

The PDF should look professional and engineering-oriented.

---

# 21. GRAPH VISUALIZATION

Create an interactive dependency graph.

Nodes:

documents

Edges:

dependencies

Color nodes based on state:

healthy
warning
stale
critical

When the user clicks a node:

show:

- document number
- discipline
- revision
- status
- dependencies
- impacted documents
- detected changes

When a revision changes, animate/highlight the affected graph.

---

# 22. CHANGE VISUALIZATION

Create a revision comparison view.

Display:

OLD REVISION
VS
NEW REVISION

Show:

- added elements
- deleted elements
- modified elements
- changed parameters
- changed positions
- changed relationships

For the MVP, do not attempt to build a full professional Revit viewer.

A simplified 2D/3D representation is sufficient.

The goal is to demonstrate the logic.

---

# 23. AI FEATURE

Only after deterministic analysis works.

Add:

"Explain this issue"

Example:

System data:

Architecture A-101 changed.
Wall moved 300 mm.
Structure S-201 depends on A-101.
S-201 still references v12.

AI response:

"The architectural revision changes the position of a wall that may influence the structural layout. S-201 has not yet been validated against A-101 v13, so it should be reviewed before the architectural revision is issued."

The AI must only explain information already produced by the deterministic engine.

Do not allow the model to invent dependencies.

Provide structured context to the LLM.

---

# 24. AI CHAT FEATURE

Optional secondary feature:

"Ask about this project"

Examples:

"What documents are affected by A-101 v13?"

"Why is this project blocked?"

"Which documents have stale dependencies?"

"What changed since revision 11?"

The assistant must query the real database and graph.

Never fabricate answers.

Every answer should be traceable to actual application data.

---

# 25. SEARCH

Implement global search.

Search by:

- document number
- document name
- discipline
- revision
- project
- status
- element ID
- issue

Search must be fast.

---

# 26. FILTERS

Add filtering by:

Project
Discipline
Status
Revision
Severity
Issue type
Date
Document type

---

# 27. NOTIFICATIONS

Create an event/notification system.

Example:

"When A-101 revision 13 is uploaded, notify users responsible for affected documents."

Notification examples:

"Architecture A-101 v13 has impacted S-201."

"Your document may be stale."

"Project is blocked from issue."

For MVP, in-app notifications are sufficient.

Email integration can be an optional future feature.

---

# 28. AUDIT LOG

Create a complete audit trail.

Track:

- login
- file upload
- revision creation
- dependency creation
- rule execution
- issue acknowledgment
- status changes
- validation
- release attempts

Example:

2026-10-06 14:32
Tayeb
uploaded
A-101 v13

2026-10-06 14:33
BIMGuard
detected
3 impacted documents

---

# 29. USER ROLES

Implement:

Admin
BIM Coordinator
Engineer
Reviewer
Viewer

Permissions should differ.

Example:

Viewer:
read only

Engineer:
upload/revise

Reviewer:
validate/approve

Admin:
manage users/projects/rules

---

# 30. RULE ENGINE

Do not hard-code every validation rule.

Build a configurable rule engine.

Example:

{
  "rule_id": "STALE_DEPENDENCY",
  "enabled": true,
  "severity": "HIGH",
  "description": "Dependent document must be validated against the latest source revision."
}

Rules should be stored in the database or structured configuration.

Allow:

enable/disable
severity configuration
thresholds

---

# 31. TECHNICAL ARCHITECTURE

Preferred stack:

Frontend:
Next.js
TypeScript
React
Tailwind CSS
a professional component library if useful

Backend:
Python
FastAPI
Pydantic
SQLAlchemy

Database:
PostgreSQL

Background tasks:
Redis + worker if genuinely necessary

BIM:
IFC parser such as IfcOpenShell

Graph:
Start with PostgreSQL relationships unless a graph database provides a clear advantage.
Do not introduce Neo4j only because it sounds impressive.

AI:
Provider abstraction supporting:
- OpenAI-compatible API
- local model option

Containerization:
Docker
Docker Compose

Testing:
pytest
Vitest/Jest
Playwright

Linting:
Ruff
MyPy where practical
ESLint
Prettier

API:
REST

OpenAPI:
automatic FastAPI documentation

---

# 32. PROJECT STRUCTURE

Create a clean monorepo.

Suggested structure:

bimguard/
│
├── apps/
│   ├── web/
│   └── api/
│
├── packages/
│   ├── shared/
│   └── domain/
│
├── services/
│   ├── change_detection/
│   ├── impact_analysis/
│   ├── validation/
│   ├── graph/
│   └── ai/
│
├── data/
│   ├── sample_projects/
│   ├── sample_ifc/
│   └── seed/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── docs/
│   ├── architecture/
│   ├── decisions/
│   ├── api/
│   └── demo/
│
├── scripts/
│
├── docker-compose.yml
├── README.md
└── LICENSE

Adjust this structure when necessary, but keep responsibilities clearly separated.

---

# 33. DATABASE DESIGN

Design a normalized relational schema.

At minimum:

users
roles
projects
documents
document_revisions
bim_elements
dependencies
detected_changes
impact_events
validation_runs
validation_issues
rules
notifications
audit_logs
ai_queries

Create:

- primary keys
- foreign keys
- indexes
- timestamps
- unique constraints
- appropriate cascade rules

Document the ER diagram.

---

# 34. API DESIGN

Create endpoints such as:

POST /projects

GET /projects

GET /projects/{id}

POST /projects/{id}/documents

GET /documents/{id}

POST /documents/{id}/revisions

GET /documents/{id}/revisions

POST /revisions/{id}/compare

GET /projects/{id}/dependencies

POST /dependencies

GET /projects/{id}/impact-analysis

POST /projects/{id}/validate

GET /validation-runs/{id}

GET /validation-runs/{id}/issues

POST /issues/{id}/acknowledge

GET /projects/{id}/graph

POST /ai/explain-issue

POST /ai/query

Use proper validation, error handling and HTTP status codes.

---

# 35. FRONTEND PAGES

Create these pages:

1. Login
2. Dashboard
3. Projects
4. Project overview
5. Documents
6. Document details
7. Revision comparison
8. Impact analysis
9. Dependency graph
10. Validation center
11. Validation report
12. Issues
13. Notifications
14. Audit log
15. Rules
16. Settings

The UI should look like professional engineering software.

Avoid flashy startup-style gradients everywhere.

Use:

- clean typography
- clear hierarchy
- dense but readable engineering tables
- status badges
- severity indicators
- graphs
- useful empty states
- confirmation dialogs
- keyboard-friendly interactions

---

# 36. DASHBOARD

The project dashboard should immediately answer:

"What is the current health of my BIM project?"

Show:

Projects
Documents
Current revisions
Stale dependencies
Critical issues
High issues
Recent changes
Issue-readiness status

Example:

PROJECT HEALTH

Documents: 48

Current revisions: 48

Stale dependencies: 3

Critical issues: 1

High issues: 4

Release readiness:

❌ BLOCKED

---

# 37. SECURITY

Implement good security practices.

At minimum:

- hashed passwords
- secure authentication
- JWT/session architecture
- role-based authorization
- input validation
- file upload validation
- file size limits
- path traversal protection
- safe file names
- no arbitrary command execution
- environment variables for secrets
- no API keys committed to Git

---

# 38. FILE HANDLING

Uploaded files must:

- be stored safely
- have generated IDs
- have checksums
- preserve metadata
- prevent duplicate uploads when appropriate

Calculate SHA-256 checksums.

Use checksum comparison to detect identical files.

---

# 39. PERFORMANCE

Design for a project with:

10–100 projects

100–10,000 documents

10,000–1,000,000 BIM elements

The MVP doesn't need perfect million-element performance, but architecture must not obviously collapse at scale.

Use:

- database indexes
- pagination
- batch operations
- background processing
- caching only where justified

Never load an entire large project into the browser unnecessarily.

---

# 40. ERROR HANDLING

Every failure should produce a useful message.

Bad:

"Something went wrong."

Good:

"Unable to compare revision A-101 v12 with v13 because revision v12 contains no supported IFC model data."

Log technical details server-side.

Return safe user-facing errors.

---

# 41. OBSERVABILITY

Add structured application logging.

Track:

- request ID
- user ID
- project ID
- document ID
- operation
- duration
- errors

Include a development logging mode.

---

# 42. TESTING REQUIREMENTS

You must create automated tests.

Minimum:

## Unit tests

Change detection
Graph traversal
Impact scoring
Stale dependency detection
Naming rule validation
Metadata validation
Release-readiness logic

## Integration tests

Upload document
Create revision
Compare revision
Generate impacts
Run validation

## End-to-end tests

Create project
Upload sample files
Create dependencies
Upload new revision
View detected changes
Run validation
See blocked release
Fix issue
Run validation again
See successful release

---

# 43. TEST CASES

At minimum test:

### Case 1
No changes.

Expected:
No impacts.

### Case 2
Architecture geometry change.

Expected:
Dependent structure becomes potentially stale.

### Case 3
Architecture metadata change only.

Expected:
Low-impact event.

### Case 4
Critical dependency changed.

Expected:
High/critical issue.

### Case 5
Indirect dependency.

Expected:
Impact propagation.

### Case 6
Circular dependency.

Expected:
No infinite traversal.

### Case 7
Duplicate file upload.

Expected:
Duplicate detection.

### Case 8
Missing metadata.

Expected:
Validation failure.

### Case 9
Stale dependency.

Expected:
Issue.

### Case 10
All issues resolved.

Expected:

PROJECT READY FOR ISSUE

---

# 44. DEMONSTRATION SCENARIO

Create one polished end-to-end demo.

Project:

"Factory Expansion – Building A"

Initial state:

Architecture A-101 v12
Structure S-201 v8
MEP M-301 v5
Quantity Q-101 v6

All valid.

Then upload:

Architecture A-101 v13

Changes:

- wall moved 300 mm
- door relocated
- room parameter changed
- one element added

BIMGuard should automatically show:

3 affected documents

Then run validation.

Result:

❌ BLOCKED

Issues:

S-201:
stale dependency

M-301:
potential spatial conflict

Q-101:
quantity information potentially outdated

Then the user acknowledges/updates dependencies.

Run validation again.

Result:

✅ READY FOR ISSUE

This should be the project's main demo.

---

# 45. SAMPLE DATA MUST BE REALISTIC

Do not generate nonsense values.

Use realistic engineering-like values:

dimensions
room numbers
wall IDs
door IDs
equipment IDs
levels
materials
coordinates
revision numbers

Document names should resemble real projects.

Examples:

A-101-L02-R13
S-201-L02-R08
M-301-L02-R06
E-040-R03
Q-101-R07

---

# 46. README

Create an excellent README.

Include:

Project overview
Business problem
Why this problem matters
Architecture
Screenshots
Demo workflow
Technology stack
Database architecture
Change detection architecture
Impact-analysis algorithm
Validation engine
AI architecture
Installation
Local development
Docker usage
Testing
API documentation
Sample credentials
Sample project
Future roadmap
Limitations

Also include:

"Why I built this"

Write it professionally, without exaggerating.

---

# 47. ARCHITECTURE DOCUMENTATION

Create:

docs/architecture/system.md

docs/architecture/change-detection.md

docs/architecture/impact-analysis.md

docs/architecture/validation-engine.md

docs/architecture/ai.md

docs/architecture/bim.md

docs/architecture/security.md

docs/architecture/database.md

docs/decisions/

Use Architecture Decision Records where appropriate.

Examples:

ADR-001:
Why FastAPI

ADR-002:
Why PostgreSQL

ADR-003:
Why IFC for MVP

ADR-004:
Why deterministic impact analysis instead of LLM reasoning

ADR-005:
Why graph relationships are represented in relational storage

---

# 48. IMPORTANT ENGINEERING PRINCIPLE

The system must follow:

DETERMINISTIC LOGIC FIRST
AI SECOND

For example:

BAD:

LLM:
"I think S-201 might be affected."

GOOD:

Rule engine:
A-101 changed.

Dependency graph:
S-201 depends_on A-101.

Revision check:
S-201 validated against A-101 v12.

Current:
A-101 v13.

Therefore:

S-201 = STALE

AI:

"Explain the technical reason in natural language."

The AI never decides the underlying truth.

---

# 49. NO FAKE CLAIMS

Never claim:

- official integration with Autodesk
- official partnership
- production deployment
- real customer usage
- real-world accuracy
- certification
- ISO compliance

unless it is actually implemented and verified.

Clearly label:

- prototype
- simulated data
- open-format BIM support
- future APS integration

---

# 50. FUTURE EXTENSIONS

Document but do not necessarily implement:

- Autodesk Platform Services integration
- Revit integration
- cloud deployment
- multi-company tenancy
- advanced 3D viewer
- IFC geometry diff
- ML-based anomaly prioritization
- mobile app
- email notifications
- Microsoft Teams/Slack integration
- approval workflow
- digital twin
- construction progress monitoring
- maintenance lifecycle analysis

---

# 51. PORTFOLIO QUALITY

This project will be shown to professional Japanese engineering/software companies.

Therefore:

- no obvious tutorial code
- no meaningless placeholder functionality
- no lorem ipsum
- no fake analytics
- no fake AI results
- no dead buttons
- no massive TODO lists
- no hard-coded demo logic pretending to be general logic

Every visible feature should actually work.

---

# 52. DEVELOPMENT PROCESS

Do NOT dump thousands of lines of code at once.

Work in controlled milestones.

MILESTONE 1
Repository setup
Docker
Database
Backend
Frontend
Authentication

MILESTONE 2
Projects/documents/revisions

MILESTONE 3
IFC import
BIM element extraction

MILESTONE 4
Revision comparison

MILESTONE 5
Dependency graph

MILESTONE 6
Impact analysis

MILESTONE 7
Validation engine

MILESTONE 8
Dashboard and visualization

MILESTONE 9
AI explanation

MILESTONE 10
Reports/audit/notifications

MILESTONE 11
Testing

MILESTONE 12
Polish/documentation/demo

At every milestone:

1. Show changed files.
2. Explain what was implemented.
3. Run tests.
4. Run the application.
5. Fix errors.
6. Do not continue if the previous milestone is broken.

---

# 53. CODING RULES

Use:

- type hints
- meaningful names
- small functions
- clean separation of concerns
- dependency injection where appropriate
- domain/service/repository separation
- explicit error handling
- comments only where they add real value

Avoid:

- giant files
- giant functions
- global state
- circular imports
- duplicated logic
- magic numbers
- hard-coded paths
- hard-coded credentials

---

# 54. WINDOWS DEVELOPMENT

The primary development environment is:

Windows 11

Development commands must work in PowerShell.

Provide:

PowerShell setup commands

Docker commands

Python commands

Node commands

Database migration commands

Testing commands

Do not assume bash-only tooling.

---

# 55. LOCAL DEVELOPMENT

The project must support:

Option A:

Docker Compose

Option B:

native development

Provide:

.env.example

README instructions

seed data

sample users

sample project

database migrations

---

# 56. DEMO LOGIN

Create development-only demo users:

admin@example.local
engineer@example.local
reviewer@example.local

Use obvious development passwords documented only for local demo purposes.

Never ship production credentials.

---

# 57. FINAL QUALITY BAR

Before declaring the project complete, verify:

- application starts
- database initializes
- sample data loads
- login works
- project creation works
- file upload works
- revision creation works
- IFC parsing works
- comparison works
- dependency graph works
- impact analysis works
- validation works
- stale detection works
- release-readiness works
- dashboard works
- graph visualization works
- AI explanation works when configured
- application still works when AI is disabled
- tests pass
- Docker works
- PowerShell setup works
- README works
- no broken links
- no dead buttons
- no obvious security problems

---

# 58. MOST IMPORTANT PRODUCT DEMO

The final demo should tell this story in under 5 minutes:

1. "Here is a BIM project."
2. "These documents are currently consistent."
3. "I upload a new architectural revision."
4. "BIMGuard automatically identifies the changes."
5. "It follows the dependency graph."
6. "It identifies potentially stale downstream documents."
7. "It explains why."
8. "The release is blocked."
9. "I resolve the issues."
10. "The project passes validation."
11. "The project is now ready for issue."

The audience should understand the value without needing to read the code.

---

# 59. FINAL PRODUCT STATEMENT

The application should ultimately communicate this concept:

"BIMGuard is a BIM information-consistency and change-impact analysis engine that detects how design revisions propagate through interconnected project information, identifies potentially stale or inconsistent downstream documents, and validates whether a project is ready for issue."

Build the system as a real software product.

Prioritize correctness, architecture, deterministic engineering logic, usability, and a polished demonstration over feature count.

Start by producing:

1. system architecture
2. domain model
3. database schema
4. repository structure
5. API design
6. frontend architecture
7. development milestones
8. exact implementation order

Then begin implementation with Milestone 1.