/**
 * queryEngine.ts
 * --------------
 * GraphQL query engine for the Data Density Heatmap.
 *
 * Responsibilities:
 *  1. Run schema introspection to discover all node types and fields
 *  2. Run aggregate queries to count total records and non-null counts per field
 *  3. Return structured data ready for the density calculator
 *
 * In the prototype this is conceptual — the density calculator (densityCalculator.ts)
 * works with mock data. In the final GSoC implementation this will connect to
 * D4CG's live Peregrine GraphQL endpoint.
 */

// ── Types ─────────────────────────────────────────────────────────────────────

export interface FieldSchema {
  name: string;
  typeName: string | null;
  isNullable: boolean;
}

export interface NodeSchema {
  nodeType: string;
  fields: FieldSchema[];
}

export interface AggregateResult {
  nodeType: string;
  totalCount: number;
  fieldCounts: Record<string, number>; // fieldName → non-null count
}

// ── System fields to exclude from density calculations ────────────────────────
const SYSTEM_FIELDS = new Set([
  "id", "type", "state", "project_id",
  "created_datetime", "updated_datetime",
  "submitter_id", "object_id", "file_state", "error_type"
]);

// Node types that are administrative, not clinical data
const SKIP_NODE_TYPES = new Set([
  "program", "project", "root", "Query", "Mutation",
  "__Schema", "__Type", "__Field", "__InputValue",
  "__EnumValue", "__Directive"
]);


// ── Step 1: Schema Introspection ──────────────────────────────────────────────

/**
 * Queries the GraphQL introspection endpoint to discover all node types
 * and their fields. Returns only clinical/data nodes, filtering out
 * system types and administrative nodes.
 */
export async function fetchSchema(
  endpoint: string,
  authToken?: string
): Promise<NodeSchema[]> {
  const introspectionQuery = `
    query IntrospectSchema {
      __schema {
        types {
          name
          kind
          fields {
            name
            type {
              name
              kind
              ofType { name kind }
            }
          }
        }
      }
    }
  `;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (authToken) {
    headers["Authorization"] = authToken;
  }

  const response = await fetch(endpoint, {
    method: "POST",
    headers,
    body: JSON.stringify({ query: introspectionQuery }),
  });

  if (!response.ok) {
    throw new Error(`Introspection failed: ${response.status} ${response.statusText}`);
  }

  const data = await response.json();
  const types = data?.data?.__schema?.types ?? [];

  // Filter to clinical OBJECT types only
  return types
    .filter((t: any) =>
      t.kind === "OBJECT" &&
      !SKIP_NODE_TYPES.has(t.name) &&
      !t.name.startsWith("__") &&
      !t.name.startsWith("_") &&
      t.fields?.length > 0
    )
    .map((t: any): NodeSchema => ({
      nodeType: t.name,
      fields: (t.fields ?? [])
        .filter((f: any) => !SYSTEM_FIELDS.has(f.name))
        .map((f: any): FieldSchema => ({
          name: f.name,
          typeName: f.type?.name ?? f.type?.ofType?.name ?? null,
          isNullable: f.type?.kind !== "NON_NULL",
        })),
    }));
}


// ── Step 2: Aggregate Queries ─────────────────────────────────────────────────

/**
 * For a given node type and list of fields, queries the Gen3 aggregation
 * endpoint to get total record count and non-null count per field.
 *
 * Gen3/Peregrine supports _aggregation queries like:
 *   { _aggregation { diagnosis { _totalCount age_at_diagnosis { _totalCount } } } }
 */
export async function fetchNodeAggregate(
  endpoint: string,
  nodeType: string,
  fields: string[],
  authToken?: string
): Promise<AggregateResult> {
  // Build the aggregation sub-query for each field
  const fieldQueries = fields
    .map(f => `${f} { _totalCount }`)
    .join("\n          ");

  const query = `
    query GetDensity_${nodeType} {
      _aggregation {
        ${nodeType} {
          _totalCount
          ${fieldQueries}
        }
      }
    }
  `;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (authToken) {
    headers["Authorization"] = authToken;
  }

  const response = await fetch(endpoint, {
    method: "POST",
    headers,
    body: JSON.stringify({ query }),
  });

  if (!response.ok) {
    throw new Error(`Aggregate query failed for ${nodeType}: ${response.statusText}`);
  }

  const data = await response.json();
  const nodeData = data?.data?._aggregation?.[nodeType] ?? {};

  const totalCount: number = nodeData._totalCount ?? 0;
  const fieldCounts: Record<string, number> = {};

  for (const field of fields) {
    fieldCounts[field] = nodeData[field]?._totalCount ?? 0;
  }

  return { nodeType, totalCount, fieldCounts };
}


/**
 * Runs aggregate queries for all node types in batches to avoid
 * overwhelming the API.
 */
export async function fetchAllAggregates(
  endpoint: string,
  schemas: NodeSchema[],
  authToken?: string,
  batchSize = 5
): Promise<AggregateResult[]> {
  const results: AggregateResult[] = [];

  for (let i = 0; i < schemas.length; i += batchSize) {
    const batch = schemas.slice(i, i + batchSize);
    const batchResults = await Promise.all(
      batch.map(s =>
        fetchNodeAggregate(
          endpoint,
          s.nodeType,
          s.fields.map(f => f.name),
          authToken
        )
      )
    );
    results.push(...batchResults);
    // Small delay between batches to be a good API citizen
    if (i + batchSize < schemas.length) {
      await new Promise(resolve => setTimeout(resolve, 200));
    }
  }

  return results;
}
