
import { expect, test, request as playwrightRequest } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join, resolve } from "node:path";
import {
  ADMIN_EMAIL,
  PASSWORD,
  apiGet,
  apiLogin,
  apiPost,
  uiLogin,
  uniqueName,
} from "./helpers";

const output = resolve(__dirname, "../../../docs/screenshots");

type ModelElement = {
  id: string;
  class: string;
  tag: string;
  name: string;
  level: string;
  room: string | null;
  properties: Record<string, string>;
  geometry: {
    location?: number[];
    rotation_deg?: number;
  };
};

function element(
  id: string,
  cls: string,
  tag: string,
  x?: number,
  room: string | null = null,
  properties: Record<string, string> = {},
): ModelElement {
  return {
    id,
    class: cls,
    tag,
    name: `${cls} ${tag}`,
    level: "L02",
    room,
    properties,
    geometry:
      x === undefined
        ? {}
        : { location: [x, 0.0, 4500.0], rotation_deg: 0.0 },
  };
}

const modelV1 = {
  schema: "bimguard.elements/1",
  elements: [
    element("w1", "IfcWall", "W-204", 10000, null, {
      "Pset_WallCommon.FireRating": "1HR",
    }),
    element("d1", "IfcDoor", "D-202A", 22000, "205"),
    element("w9", "IfcWall", "W-9", 5000),
  ],
};

const modelV2 = {
  schema: "bimguard.elements/1",
  elements: [
    element("w1", "IfcWall", "W-204", 10300, null, {
      "Pset_WallCommon.FireRating": "2HR",
    }),
    element("d1", "IfcDoor", "D-202A", 22000, "204"),
    element("w2", "IfcWall", "W-207", 25000),
  ],
};

async function uploadRevision(
  token: string,
  documentId: string,
  revisionNumber: number,
  model: typeof modelV1,
  summary: string,
) {
  const ctx = await playwrightRequest.newContext({
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });

  try {
    const response = await ctx.post(
      `${process.env.E2E_API_URL ?? "http://127.0.0.1:8001"}/documents/${documentId}/revisions`,
      {
        multipart: {
          file: {
            name: `architecture_v${revisionNumber}.json`,
            mimeType: "application/json",
            buffer: Buffer.from(JSON.stringify(model, null, 2)),
          },
          revision_number: String(revisionNumber),
          change_summary: summary,
        },
      },
    );

    const body = await response.text();

    if (!response.ok()) {
      throw new Error(
        `Revision upload failed (${response.status()}): ${body}`,
      );
    }

    return JSON.parse(body);
  } finally {
    await ctx.dispose();
  }
}

test("capture populated BIMGuard README screenshots", async ({ page }) => {
  await mkdir(output, { recursive: true });

  const token = await apiLogin(ADMIN_EMAIL, PASSWORD);

  // Create an isolated demonstration project.
  const project = await apiPost(token, "/projects", {
    name: uniqueName("BIMGuard README Demo"),
    client: "BIMGuard Demonstration",
    description:
      "Portfolio demonstration containing model revisions, dependencies, impact analysis and release validation.",
  });

  // Two documents allow us to demonstrate a real dependency graph.
  const architecture = await apiPost(
    token,
    `/projects/${project.id}/documents`,
    {
      document_number: "A-001",
      name: "Level 02 Architectural Model",
      discipline: "architecture",
      author: "BIMGuard Demo",
      source_system: "BIMGuard JSON Demo",
    },
  );

  const structure = await apiPost(
    token,
    `/projects/${project.id}/documents`,
    {
      document_number: "S-001",
      name: "Level 02 Structural Coordination Model",
      discipline: "structure",
      author: "BIMGuard Demo",
      source_system: "BIMGuard JSON Demo",
    },
  );

  // Upload two real BIMGuard JSON model revisions.
  await uploadRevision(
    token,
    architecture.id,
    1,
    modelV1,
    "Initial architectural model",
  );

  await uploadRevision(
    token,
    architecture.id,
    2,
    modelV2,
    "Moved wall, updated fire rating, revised room assignment, removed and added elements",
  );

  // Wait until background extraction has completed successfully.
  await expect
    .poll(
      async () => {
        const revisions = await apiGet(
          token,
          `/documents/${architecture.id}/revisions`,
        );

        return (
          Array.isArray(revisions) &&
          revisions.length >= 2 &&
          revisions.every((revision: { extraction_status: string }) =>
            revision.extraction_status === "ok"
          )
        );
      },
      { timeout: 90_000, intervals: [1000, 2000, 3000] },
    )
    .toBe(true);

  const revisions = await apiGet(
    token,
    `/documents/${architecture.id}/revisions`,
  );

  const latestRevision = revisions.find(
    (revision: { revision_number: number }) =>
      revision.revision_number === 2,
  );

  expect(latestRevision, "Expected architecture revision 2").toBeTruthy();

  // Generate the comparison explicitly, rather than relying only on auto-compare.
  const comparison = await apiPost(
    token,
    `/revisions/${latestRevision.id}/compare`,
    {},
  );

  expect(comparison.total_changes).toBe(5);

  // The structural document depends on the architectural document.
  // It was last validated against architecture revision 1, so revision 2
  // makes this relationship stale.
  await apiPost(token, "/dependencies", {
    source_document_id: structure.id,
    target_document_id: architecture.id,
    relationship_type: "depends_on",
    confidence: 1,
    reason:
      "Structural coordination depends on the current architectural layout.",
    validated_against_revision: 1,
  });

  // Generate impact analysis and release validation data.
  await apiPost(
    token,
    `/projects/${project.id}/impact-analysis`,
    {},
  );

  await apiPost(
    token,
    `/projects/${project.id}/validate`,
    {},
  );

  // Confirm the validation run exists before taking screenshots.
  await expect
    .poll(
      async () => {
        const run = await apiGet(
          token,
          `/projects/${project.id}/validation-runs/latest`,
        );
        return Boolean(run?.id);
      },
      { timeout: 30_000, intervals: [1000, 2000] },
    )
    .toBe(true);

  // Sign into the actual web application.
  await uiLogin(page, ADMIN_EMAIL, PASSWORD);

  // Dashboard: the new demo project should be present.
  await page.goto("/dashboard");
  await expect(
    page.getByText(project.name, { exact: false }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: join(output, "dashboard.png"),
    fullPage: true,
  });

  // Project detail: two documents and their revisions.
  await page.goto(`/projects/${project.id}`);
  await expect(
    page.getByText(project.name, { exact: false }).first(),
  ).toBeVisible();
  await expect(page.getByText("A-001").first()).toBeVisible();
  await expect(page.getByText("S-001").first()).toBeVisible();
  await page.screenshot({
    path: join(output, "project-detail.png"),
    fullPage: true,
  });

  // Comparison: five actual model changes.
  await page.goto(`/revisions/${latestRevision.id}/compare`);
  await expect(page.getByRole("row").filter({ hasText: "W-207" })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "W-9" })).toBeVisible();
  await page.screenshot({
    path: join(output, "model-comparison.png"),
    fullPage: true,
  });

  // Dependency graph and relationship table.
  await page.goto(`/projects/${project.id}/dependencies`);
  await expect(
    page.getByRole("button", {
      name: /A-001 Level 02 Architectural Model/,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: /S-001 Level 02 Structural Coordination Model/,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("row").filter({
      hasText: "S-001 depends on A-001",
    }),
  ).toBeVisible();
  await page.screenshot({
    path: join(output, "dependency-graph.png"),
    fullPage: true,
  });

  // Impact analysis: demonstrate the consequences of the model change.
  await page.goto(`/projects/${project.id}/impact`);
  await expect(
    page.getByRole("heading", { name: /impact/i }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: join(output, "impact-analysis.png"),
    fullPage: true,
  });

  // Validation: show the actual release-readiness result and issues.
  await page.goto(`/projects/${project.id}/validation`);
  await expect(
    page.getByRole("button", { name: /validate for issue/i }),
  ).toBeVisible();
  await expect(
    page.getByText(/blocked|ready|warning/i).first(),
  ).toBeVisible();
  await page.screenshot({
    path: join(output, "validation.png"),
    fullPage: true,
  });

  // Readiness report: populated project metrics.
  await page.goto(`/projects/${project.id}/reports`);
  await expect(
    page.getByRole("heading", { name: /reports/i }).first(),
  ).toBeVisible();
  await expect(page.getByText("A-001").first()).toHaveCount(0);
  await page.screenshot({
    path: join(output, "readiness-report.png"),
    fullPage: true,
  });

  // Audit: activity generated by the demo workflow.
  await page.goto("/audit");
  await expect(
    page.getByRole("heading", { name: /audit log/i }),
  ).toBeVisible();
  await page.screenshot({
    path: join(output, "audit-log.png"),
    fullPage: true,
  });

  console.log(`Populated README screenshots saved to ${output}`);
});
