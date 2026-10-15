# AI explanation layer

## Goals

- Explain findings the deterministic engines already produced.
- Never decide anything. Never read the database. Never invent identifiers.
- Work with AI disabled. Templates are always sufficient.
- Fail safe: provider errors or grounding violations fall back to the template.

## Non-goals

- Writing to the database.
- Analysing models, running rules, or computing impacts.
- Replacing the deterministic answer with a "better" one.

## Data flow

    question
        |
        v
    Router (rules) --> QuestionType
        |
        v
    Retrieval (DB read) --> Facts
        |
        v
    Templates --> template_answer  (always available)
        |
        v
    If AI enabled and under hourly limit:
        Provider.complete(facts) --> reply
        Grounding.check(reply, facts)
            ok   --> return reply (path="ai")
            fail --> return template_answer (violations recorded)
    Log AIQuery (question, path, facts, violations, model_name)

## Facts

A Fact is one short sentence with exact identifiers, plus a kind and a list
of identifiers. Facts are built only from engine output: dependency edges,
impact events, validation issues, detected changes.

## Router

Ordered rules, first match wins. Recognises: affected-by, affects, status,
validation, dependencies, summary. Unrecognised questions route to UNKNOWN
and get a fixed help message.

## Grounding check

Extracts identifiers from the reply (document numbers, element tags,
revisions, links). Any identifier not present in the fact set is a
violation. On any violation the whole reply is discarded and the template
answer is used instead, with the violations stored on the AIQuery row.

## Hourly limit

The orchestrator counts AIQuery rows with path="ai" created in the last
60 minutes, per project. At or above the limit, the template is used.
Template rows are not counted against the limit.

## Provider configuration

Set these environment variables to enable AI:

- AI_BASE_URL - e.g. https://api.openai.com/v1 or http://localhost:11434/v1
- AI_API_KEY - optional for local servers
- AI_MODEL - e.g. gpt-4o-mini or llama3.1:8b

Any OpenAI-compatible server works: OpenAI, Ollama, LM Studio, vLLM.

## Testing

- ScriptedProvider returns deterministic replies for tests.
- httpx.MockTransport tests the real client against a scripted transport.
- API tests inject the provider via app.dependency_overrides.

## Failure modes and fallbacks

| Failure                       | Behaviour                                |
|-------------------------------|------------------------------------------|
| AI disabled                   | Template answer, path="template"         |
| Provider not configured       | Template answer, path="template"         |
| Provider timeout / HTTP error | Template answer, path="template"         |
| Malformed provider response   | Template answer, path="template"         |
| Grounding violation           | Template answer, violations recorded     |
| Hourly limit reached          | Template answer, path="template"         |
