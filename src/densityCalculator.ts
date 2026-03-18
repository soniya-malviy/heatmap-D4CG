/**
 * densityCalculator.ts
 * --------------------
 * Calculates data density scores from aggregate query results.
 *
 * Density formula:
 *   density_score = (non_null_count / total_record_count) × 100
 *
 * Edge cases handled:
 *   - Node with zero records → density = null (not 0%, to avoid misleading)
 *   - Field count > total count → capped at 100% (data anomaly)
 *   - System fields are excluded upstream in queryEngine.ts
 */

import type { AggregateResult } from "./queryEngine";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface FieldDensity {
  fieldName: string;
  totalCount: number;      // total records in this node
  nonNullCount: number;    // records where this field is non-null
  densityScore: number | null; // 0–100, or null if no records exist
  category: DensityCategory;
}

export interface NodeDensity {
  nodeType: string;
  totalRecords: number;
  fields: FieldDensity[];
  overallDensity: number | null; // average across all fields
}

export type DensityCategory = "sparse" | "partial" | "complete" | "empty";

// ── Thresholds (configurable via heatmap.config.json) ─────────────────────────
export interface DensityThresholds {
  low: number;  // below this = sparse (default 33)
  mid: number;  // below this = partial (default 66)
}

const DEFAULT_THRESHOLDS: DensityThresholds = { low: 33, mid: 66 };


// ── Core calculation ──────────────────────────────────────────────────────────

/**
 * Calculates density score for a single field.
 */
export function calculateFieldDensity(
  fieldName: string,
  totalCount: number,
  nonNullCount: number,
  thresholds: DensityThresholds = DEFAULT_THRESHOLDS
): FieldDensity {
  let densityScore: number | null = null;
  let category: DensityCategory = "empty";

  if (totalCount === 0) {
    // No records in this node at all
    densityScore = null;
    category = "empty";
  } else {
    // Cap at 100 in case of data anomalies
    const raw = (nonNullCount / totalCount) * 100;
    densityScore = Math.min(100, Math.round(raw * 10) / 10);

    if (densityScore <= thresholds.low) {
      category = "sparse";
    } else if (densityScore <= thresholds.mid) {
      category = "partial";
    } else {
      category = "complete";
    }
  }

  return { fieldName, totalCount, nonNullCount, densityScore, category };
}


/**
 * Calculates density scores for all fields in a node type.
 */
export function calculateNodeDensity(
  aggregate: AggregateResult,
  thresholds: DensityThresholds = DEFAULT_THRESHOLDS
): NodeDensity {
  const fields: FieldDensity[] = Object.entries(aggregate.fieldCounts).map(
    ([fieldName, nonNullCount]) =>
      calculateFieldDensity(fieldName, aggregate.totalCount, nonNullCount, thresholds)
  );

  // Overall density = average of all field scores (ignoring nulls)
  const scoredFields = fields.filter(f => f.densityScore !== null);
  const overallDensity =
    scoredFields.length > 0
      ? Math.round(
          scoredFields.reduce((sum, f) => sum + (f.densityScore as number), 0) /
            scoredFields.length *
            10
        ) / 10
      : null;

  return {
    nodeType: aggregate.nodeType,
    totalRecords: aggregate.totalCount,
    fields,
    overallDensity,
  };
}


/**
 * Calculates density for all node types.
 * Returns sorted by overall density ascending (sparsest first)
 * so the most problematic nodes appear at the top.
 */
export function calculateAllDensities(
  aggregates: AggregateResult[],
  thresholds: DensityThresholds = DEFAULT_THRESHOLDS
): NodeDensity[] {
  return aggregates
    .map(a => calculateNodeDensity(a, thresholds))
    .sort((a, b) => {
      // Nodes with no records go last
      if (a.overallDensity === null) return 1;
      if (b.overallDensity === null) return -1;
      return a.overallDensity - b.overallDensity;
    });
}


/**
 * Returns a summary of the full dataset's completeness.
 */
export function summariseDensity(nodeDensities: NodeDensity[]): {
  totalNodes: number;
  totalFields: number;
  overallScore: number | null;
  sparseFields: { nodeType: string; fieldName: string; score: number }[];
} {
  const allFields = nodeDensities.flatMap(n => n.fields);
  const scoredFields = allFields.filter(f => f.densityScore !== null);

  const overallScore =
    scoredFields.length > 0
      ? Math.round(
          (scoredFields.reduce((s, f) => s + (f.densityScore as number), 0) /
            scoredFields.length) *
            10
        ) / 10
      : null;

  // Top 10 sparsest fields for the summary panel
  const sparseFields = scoredFields
    .filter(f => f.category === "sparse")
    .map(f => {
      const node = nodeDensities.find(n =>
        n.fields.some(nf => nf.fieldName === f.fieldName)
      );
      return {
        nodeType: node?.nodeType ?? "unknown",
        fieldName: f.fieldName,
        score: f.densityScore as number,
      };
    })
    .sort((a, b) => a.score - b.score)
    .slice(0, 10);

  return {
    totalNodes: nodeDensities.length,
    totalFields: allFields.length,
    overallScore,
    sparseFields,
  };
}
