# Advanced Patterns & Conventions (FastAPI + Pydantic + Neo4j/GraphQL)

Concise examples to keep codebases sharp and testable. All snippets are Python unless noted.

## Pydantic
- Prefer explicit field types and forbid extras:
  ```python
  from pydantic import BaseModel, Field, ConfigDict

  class PredictPayload(BaseModel):
      model_config = ConfigDict(extra="forbid")
      rows: list[dict] = Field(..., min_length=1)
      version: str | None = None
  ```
- Aliases for external field names:
  ```python
  class OrderDTO(BaseModel):
      restaurant_guid: str = Field(alias="restaurantGuid")
      business_date: str = Field(alias="businessDate")
  ```
- Dataclasses + validation:
  ```python
  from pydantic.dataclasses import dataclass
  @dataclass
  class Watermark:
      value: str
  ```

## FastAPI routers (DI-friendly)
- Build routers via factories; inject clients:
  ```python
  def make_router(ingest_svc):
      router = APIRouter()
      @router.post("/incremental")
      def run():
          return ingest_svc.run_incremental()
      return router
  ```

## Dataclasses & magic methods
- Rich dataclasses with ordering/fingerprint:
  ```python
  from dataclasses import dataclass, field
  import hashlib

  @dataclass(order=True)
  class PromptModule:
      name: str
      prompt: str
      version: int = 1
      history: list[float] = field(default_factory=list, compare=False)

      def fingerprint(self) -> str:
          key = f"{self.name}:{self.version}:{self.prompt}"
          return hashlib.md5(key.encode()).hexdigest()[:8]

      def __repr__(self):
          return f"<PromptModule {self.name} v{self.version} {self.fingerprint()}>"
  ```

## Metaclasses / decorators (use sparingly)
- Simple registry via decorator (clearer than metaclass):
  ```python
  REGISTRY = {}
  def register(name):
      def deco(fn):
          REGISTRY[name] = fn
          return fn
      return deco
  ```
- Metaclass for enforcing attributes (only when necessary):
  ```python
  class RequiresName(type):
      def __call__(cls, *args, **kwargs):
          obj = super().__call__(*args, **kwargs)
          if not getattr(obj, "name", None):
              raise TypeError("name is required")
          return obj
  class Tool(metaclass=RequiresName):
      name: str
  ```

## Dynamic configuration / aliasing
- Promote env→config dataclasses:
  ```python
  @dataclass
  class Neo4jConfig:
      uri: str
      user: str
      password: str
      database: str | None = None

      @classmethod
      def from_env(cls):
          import os
          return cls(
              uri=os.environ["NEO4J_URI"],
              user=os.getenv("NEO4J_USER", "neo4j"),
              password=os.environ["NEO4J_PASSWORD"],
              database=os.getenv("NEO4J_DATABASE"),
          )
  ```

## GraphQL (Strawberry, Neo4j @cypher)
- Keep resolvers thin; push work to services; use dataloaders to avoid N+1.
- Use `@cypher` for computed fields sparingly and ensure indexed predicates:
  ```graphql
  type Restaurant @node(label: "Restaurant") {
    id: ID! @id
    name: String @index
    topEmployees(limit: Int = 5): [Employee]
      @cypher(
        statement: """
        MATCH (this)<-[:WORKS_AT_RESTAURANT]-(e:Employee)
        RETURN e ORDER BY e.score DESC LIMIT $limit
        """
      )
  }
  ```

## Ingestion patterns (Snowflake → Neo4j)
- Constrain first: create unique constraints on GUIDs.
- Batch with UNWIND; small transactions; MERGE for idempotency:
  ```cypher
  UNWIND $rows AS row
  MERGE (o:Order {guid: row.GUID})
    ON CREATE SET o.businessDate = date(row.BUSINESS_DATE)
    ON MATCH SET o.lastModifiedAt = datetime()
  MERGE (r:Restaurant {restaurantGuid: row.RESTAURANTGUID})
  MERGE (o)-[:PLACED_AT_RESTAURANT]->(r);
  ```

## Meta-prompting (GEPA / LLM tools)
- Keep prompts deterministic; include guardrails; carry examples; forbid disallowed labels/relationships; enforce tenant filters.
- For generated Cypher/SQL: require LIMIT defaults, ALLOWLIST labels/columns, and reject writes in read-mode.

## Error handling & __doc__
- Always document modules/classes with succinct `__doc__`.
- Raise HTTP 4xx/5xx with clear messages; log trace separately.
- Separate user-facing errors from internal exceptions; avoid leaking creds.

## Testing
- Unit-test routers with dependency overrides; mock clients.
- Cypher/SQL lint: smoke-EXPLAIN on generated queries in tests.
- Snapshot prompts/configs for audit (fingerprint and version them).
